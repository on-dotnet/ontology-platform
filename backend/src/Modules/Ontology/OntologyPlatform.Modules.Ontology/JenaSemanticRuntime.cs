using System.Diagnostics;
using System.Diagnostics.Metrics;
using System.Net;
using System.Runtime.CompilerServices;
using System.Text;
using System.Text.Json;
using Microsoft.Extensions.Configuration;
using OntologyPlatform.Contracts;
using OntologyPlatform.Modules.Ontology.Domain;

namespace OntologyPlatform.Modules.Ontology;

/// <summary>复用官方Fuseki RIOT/GSP/SHACL端点的受控适配器，不接受用户查询或URL。</summary>
public sealed class JenaSemanticRuntime : ISemanticRuntime
{
    /// <summary>只记录固定阶段与状态，不记录用户源或查询文本。</summary>
    private static readonly ActivitySource Activities = new("OntologyPlatform.Ontology");

    /// <summary>低基数运行时指标，不以主体/厂区/实体作为标签。</summary>
    private static readonly Meter Metrics = new("OntologyPlatform.Ontology");

    /// <summary>操作实际耗时，单位毫秒，标签仅固定操作和结果。</summary>
    private static readonly Histogram<double> Duration = Metrics.CreateHistogram<double>("ontology.semantic.duration", "ms");

    /// <summary>整进程最多两个语义操作同时占用运行时。</summary>
    private static readonly SemaphoreSlim Slots = new(2, 2);

    /// <summary>使用由组合根禁用重定向的HTTP客户端工厂。</summary>
    private readonly IHttpClientFactory clients;

    /// <summary>固定内存验证dataset。</summary>
    private readonly Uri validation;

    /// <summary>固定正式TDB2 dataset。</summary>
    private readonly Uri published;

    /// <summary>可测试的真实时间来源。</summary>
    private readonly TimeProvider clock;

    /// <summary>验证启动配置为固定回环地址，任何请求不能覆盖。</summary>
    /// <param name="clients">受控客户端工厂。</param>
    /// <param name="configuration">仅读取固定dataset配置。</param>
    /// <param name="clock">校验事实时间。</param>
    public JenaSemanticRuntime(IHttpClientFactory clients, IConfiguration configuration, TimeProvider clock)
    {
        this.clients = clients;
        validation = Origin(configuration["Semantics:ValidationOrigin"]);
        published = Origin(configuration["Semantics:PublishedOrigin"]);
        this.clock = clock;
    }

    /// <summary>真实解析全部源码并映射本体投影，保留未知结构的完整源码。</summary>
    public Task<SemanticAnalysis> AnalyzeAsync(SourceBundle sources, long revision, CancellationToken cancellationToken) =>
        Execute(async (graphs, token) =>
        {
            // 四类源码分别解析，不允许前一个源的prefix/base污染下一个源。
            var parsed = await ParseSourcesAsync(sources, graphs, token);
            return Analysis(sources, revision, parsed[0]);
        }, cancellationToken);

    /// <summary>在通过安全清单后执行官方SHACL，HTTP200不代表conforms。</summary>
    public Task<SemanticValidationReport> ValidateAsync(SourceBundle sources, CancellationToken cancellationToken) =>
        Execute(async (graphs, token) =>
        {
            // 本轮支持边界优先于SHACL执行，未支持OWL和imports不可发布。
            var parsed = await ParseSourcesAsync(sources, graphs, token);
            // 所有本体/词汇/数据图都必须符合可回验的无空白发布子集。
            var diagnostics = Support(parsed[0].Concat(parsed[2]).Concat(parsed[3]).ToArray());
            if (diagnostics.Length > 0)
                return new SemanticValidationReport
                {
                    ReportId = Guid.NewGuid().ToString("N"),
                    Hashes = JenaRdfCodec.Hashes(sources),
                    Kind = ValidationKind.OwlSupport,
                    Conforms = false,
                    Issues = diagnostics.Select(diagnostic => new ValidationIssue { Severity = DiagnosticSeverity.Error, Message = diagnostic.Message, FocusNode = diagnostic.FocusNode, Path = diagnostic.Path, SourceId = "ontology" }).ToArray(),
                    RawReportHash = OntologyRules.Hash(JsonSerializer.Serialize(diagnostics)),
                    ValidatedAtUtc = clock.GetUtcNow()
                };
            // 图在内存独占暂存，用完整已解析三元组合并，完全不触发imports网络请求。
            var combined = parsed[0].Concat(parsed[2]).Concat(parsed[3]).ToArray();
            // Fuseki不保留空命名图；仅在核实从不写入的默认图为空时使用官方default目标。
            var graph = "default";
            if (combined.Length > 0) graph = await LoadAsync(string.Join('\n', combined.Select(JenaRdfCodec.Triple)), graphs, token);
            else if (JenaRdfCodec.Parse(await SendAsync(validation, "data?default", HttpMethod.Get, null, "application/rdf+json", token)).Length != 0)
                throw new SemanticOperationException(503, "validation_default_not_empty");
            // 原始标准报告字节参与散列，定位字段由真实报告映射。
            var raw = await SendAsync(validation, "shacl?graph=" + Uri.EscapeDataString(graph), HttpMethod.Post, SourceDocument(sources.ShapesTurtle, 1), "application/rdf+json", token);
            // RDF报告不按HTTP成功猜测，而明确读取标准conforms谓词。
            var report = JenaRdfCodec.Parse(raw);
            // 必须恰好一个报告布尔结果，坏响应作为依赖故障关闭。
            var conforms = report.Where(triple => triple.Predicate == ShapePolicy.Sh + "conforms").ToArray();
            if (conforms.Length != 1 || conforms[0].Object.Value is not ("true" or "false")) throw new SemanticOperationException(503, "shacl_response_invalid");
            return new SemanticValidationReport
            {
                ReportId = Guid.NewGuid().ToString("N"),
                Hashes = JenaRdfCodec.Hashes(sources),
                Kind = ValidationKind.ShaclCore,
                Conforms = conforms[0].Object.Value == "true",
                Issues = Issues(report),
                RawReportHash = OntologyRules.Hash(raw),
                ValidatedAtUtc = clock.GetUtcNow()
            };
        }, cancellationToken);

    /// <summary>精确编辑完整无未知图；无操作保留原文字节，复杂图阻断。</summary>
    public Task<SourceBundle> ApplyEditAsync(SourceBundle sources, SemanticEdit edit, CancellationToken cancellationToken) =>
        Execute(async (graphs, token) =>
        {
            // 使用真正RDF解析后的完整图，不从节点/边投影重建本体。
            var parsed = await ParseSourcesAsync(sources, graphs, token);
            if (Support(parsed[0]).Length != 0) throw new SemanticOperationException(422, "structural_edit_unsupported");
            JenaRdfCodec.Iri(edit.SubjectIri);
            JenaRdfCodec.Iri(edit.PredicateIri);
            if (edit.OldObject?.Kind == RdfTermKind.Blank || edit.NewObject?.Kind == RdfTermKind.Blank || (edit.OldObject is null && edit.NewObject is null))
                throw new SemanticOperationException(422, "rdf_edit_invalid");
            if (!EditablePredicate(edit.PredicateIri, parsed[0])) throw new SemanticOperationException(422, "predicate_edit_unsupported");
            // 原始精确三元组集合只移除显式指定的旧值，不扩大到整个谓词。
            var triples = parsed[0].ToList();
            // 主体项来自已经校验的完整IRI。
            var subject = new RdfTerm { Kind = RdfTermKind.Iri, Value = edit.SubjectIri };
            if (edit.OldObject is not null && !triples.Remove(new RdfTriple { Subject = subject, Predicate = edit.PredicateIri, Object = edit.OldObject }))
                throw new SemanticOperationException(409, "edit_source_conflict");
            if (edit.NewObject is not null) triples.Add(new RdfTriple { Subject = subject, Predicate = edit.PredicateIri, Object = edit.NewObject });
            if (edit.OldObject == edit.NewObject) return sources;
            // 重复新增也为no-op，不丢掉注释或改变权威源码字节。
            var result = triples.Distinct().ToArray();
            if (result.ToHashSet().SetEquals(parsed[0])) return sources;
            if (Support(result).Length != 0) throw new SemanticOperationException(422, "structural_edit_unsupported");
            return sources with { OntologyTurtle = JenaRdfCodec.Canonical(result) + "\n" };
        }, cancellationToken);

    /// <summary>以releaseId服务器派生的独占图部署，源散列或图名不符即失败。</summary>
    public Task DeployAsync(ReleaseManifest manifest, SourceBundle sources, CancellationToken cancellationToken) =>
        Execute(async (graphs, token) =>
        {
            CheckManifest(manifest, sources);
            // 部署前在内存真实解析，未知复杂公理不进入正式发布。
            var parsed = await ParseSourcesAsync(sources, graphs, token);
            if (Support(parsed[0].Concat(parsed[2]).Concat(parsed[3]).ToArray()).Length != 0) throw new SemanticOperationException(422, "publication_unsupported");
            await SendAsync(published, "data?graph=" + Uri.EscapeDataString(manifest.OntologyGraphIri), HttpMethod.Put, string.Join('\n', parsed[0].Concat(parsed[2]).Select(JenaRdfCodec.Triple)), "text/plain", token);
            await SendAsync(published, "data?graph=" + Uri.EscapeDataString(manifest.DataGraphIri), HttpMethod.Put, string.Join('\n', parsed[3].Select(JenaRdfCodec.Triple)), "text/plain", token);
            return true;
        }, cancellationToken);

    /// <summary>回读正式图与实际内存解析结果逐项核对，typed literal改写必须失败。</summary>
    public Task<bool> VerifyAsync(ReleaseManifest manifest, SourceBundle sources, CancellationToken cancellationToken) =>
        Execute(async (graphs, token) =>
        {
            CheckManifest(manifest, sources);
            // 权威源重新解析用于实际图语义对账。
            var parsed = await ParseSourcesAsync(sources, graphs, token);
            // 正式图通过固定GSP读取，任何缺失不视为空成功。
            var ontology = await ReadGraphAsync(published, manifest.OntologyGraphIri, token);
            // 数据图与本体图独立对账。
            var data = await ReadGraphAsync(published, manifest.DataGraphIri, token);
            if (JenaRdfCodec.Canonical(ontology) != JenaRdfCodec.Canonical(parsed[0].Concat(parsed[2]).Distinct().ToArray()) || JenaRdfCodec.Canonical(data) != JenaRdfCodec.Canonical(parsed[3])) return false;
            // 使用实际回读的正式本体和事实合并验证，避免漏掉subClassOf等父类target。
            var verificationGraph = await LoadAsync(string.Join('\n', ontology.Concat(data).Select(JenaRdfCodec.Triple)), graphs, token);
            // 此图内容来自正式TDB2实际回读，绝不拿原始源替代验证中的事实。
            var raw = await SendAsync(validation, "shacl?graph=" + Uri.EscapeDataString(verificationGraph), HttpMethod.Post, SourceDocument(sources.ShapesTurtle, 1), "application/rdf+json", token);
            return JenaRdfCodec.Parse(raw).Any(triple => triple.Predicate == ShapePolicy.Sh + "conforms" && triple.Object.Value == "true");
        }, cancellationToken);

    /// <summary>读取固定发布图，缺失源保持503，不伪造空结果。</summary>
    public Task<PublishedRdfData> ReadPublishedAsync(AssetVersionSnapshot snapshot, CancellationToken cancellationToken) =>
        Execute(async (_, token) =>
        {
            CheckGraphs(snapshot.ReleaseId, snapshot.OntologyGraphIri, snapshot.DataGraphIri);
            return new PublishedRdfData
            {
                OntologyTriples = await ReadGraphAsync(published, snapshot.OntologyGraphIri, token),
                DataTriples = await ReadGraphAsync(published, snapshot.DataGraphIri, token)
            };
        }, cancellationToken);

    /// <summary>外层并发和总时限预算覆盖完整操作，取消后仍有独立清理预算。</summary>
    private async Task<T> Execute<T>(Func<List<string>, CancellationToken, Task<T>> operation, CancellationToken cancellationToken, [CallerMemberName] string phase = "")
    {
        if (!await Slots.WaitAsync(0, cancellationToken)) throw new SemanticOperationException(429, "semantic_busy");
        // 只有固定公共方法名可成为阶段标签，不接受用户提供的phase。
        using var activity = Activities.StartActivity("ontology.semantic");
        activity?.SetTag("ontology.phase", phase);
        // 单调时钟用于真实延迟，不把墙钟跳变算作性能数据。
        var started = Stopwatch.GetTimestamp();
        // 默认失败，只有操作真正完成才记录成功状态。
        var outcome = "failed";
        // 当前请求独占图只存在本次操作内，finally一定尝试删除。
        var graphs = new List<string>();
        // 整个操作最多五秒，不按每个HTTP请求重新给予五秒。
        using var budget = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        budget.CancelAfter(TimeSpan.FromSeconds(5));
        try
        {
            // 真实执行结果先完成，后标记成功；清理仍在finally执行。
            var result = await operation(graphs, budget.Token);
            outcome = "completed";
            return result;
        }
        catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested) { throw new SemanticOperationException(503, "semantic_timeout"); }
        catch (HttpRequestException) { throw new SemanticOperationException(503, "semantic_unavailable"); }
        catch (JsonException) { throw new SemanticOperationException(503, "rdf_response_invalid"); }
        finally
        {
            // 清理不继承用户取消，但自身至多两秒，不无限占用槽位。
            using var cleanup = new CancellationTokenSource(TimeSpan.FromSeconds(2));
            try
            {
                foreach (var graph in graphs)
                    await SendAsync(validation, "data?graph=" + Uri.EscapeDataString(graph), HttpMethod.Delete, null, "text/plain", cleanup.Token);
            }
            catch (Exception exception) when (exception is HttpRequestException or OperationCanceledException or SemanticOperationException) { /* 依赖故障时内存暂存图等待运行时重启清理，不能泄露源码到日志。 */ }
            finally
            {
                activity?.SetStatus(outcome == "completed" ? ActivityStatusCode.Ok : ActivityStatusCode.Error);
                Duration.Record(Stopwatch.GetElapsedTime(started).TotalMilliseconds, new KeyValuePair<string, object?>("operation", phase), new KeyValuePair<string, object?>("outcome", outcome));
                Slots.Release();
            }
        }
    }

    /// <summary>分别由RIOT解析四类源并执行Shape安全检查，计算总三元组预算。</summary>
    private async Task<RdfTriple[][]> ParseSourcesAsync(SourceBundle sources, List<string> graphs, CancellationToken token)
    {
        if (sources is null || sources.OntologyTurtle is null || sources.ShapesTurtle is null || sources.DataTurtle is null || !OntologyRules.WithinSourceBudget(sources.OntologyTurtle, sources.ShapesTurtle, sources.VocabularyTurtle, sources.DataTurtle))
            throw new SemanticOperationException(413, "source_byte_budget");
        // 各源数组顺序与公共SourceBundle一致。
        var result = new List<RdfTriple[]>();
        // 稳定文档索引定义未显式BASE源码的相对IRI基址，不包含随机端口或图ID。
        var sourceIndex = 0;
        foreach (var source in new[] { sources.OntologyTurtle, sources.ShapesTurtle, sources.VocabularyTurtle, sources.DataTurtle })
        {
            if (string.IsNullOrEmpty(source)) { result.Add([]); sourceIndex++; continue; }
            // 仅临时解析图携带不可猜的完整三元组，令合法零三元组文档也可通过GSP回读。
            var markerIri = "urn:ontology-platform:parse-marker:" + Guid.NewGuid().ToString("N");
            // 全绝对IRI且前置于文档，用户BASE/prefix/末尾注释不能改变标记语义或修复坏语法。
            var marker = new RdfTriple { Subject = new RdfTerm { Kind = RdfTermKind.Iri, Value = markerIri }, Predicate = markerIri, Object = new RdfTerm { Kind = RdfTermKind.Iri, Value = markerIri } };
            // 原文仅用于本次RIOT请求，绝不改写权威源码或其散列。
            var graph = await LoadAsync(JenaRdfCodec.Triple(marker) + "\n" + SourceDocument(source, sourceIndex++), graphs, token);
            // 丢图仍由GSP返回503；即使回读200也必须包含本次标记，不能把重启/替换当空图。
            var parsed = await ReadGraphAsync(validation, graph, token);
            if (parsed.Count(triple => triple == marker) != 1) throw new SemanticOperationException(503, "temporary_graph_incomplete");
            // 精确剔除本次标记后才做预算、Shape、投影、编辑与正式部署，不按命名空间丢业务公理。
            result.Add(parsed.Where(triple => triple != marker).ToArray());
        }
        if (result.Sum(triples => triples.Length) > 5000) throw new SemanticOperationException(422, "rdf_triple_budget");
        ShapePolicy.Check(result[1]);
        return result.ToArray();
    }

    /// <summary>提供固定的解析文档基址；用户显式BASE仍按Turtle规范覆盖，不进行网络抓取。</summary>
    private static string SourceDocument(string source, int index) => "@base <https://ontology.invalid/source/" + index.ToString(System.Globalization.CultureInfo.InvariantCulture) + "/> .\n" + source.TrimStart('\uFEFF');

    /// <summary>使用随机服务器IRI创建暂存图，登记早于写入以便失败也清理。</summary>
    private async Task<string> LoadAsync(string source, List<string> graphs, CancellationToken token)
    {
        // 随机标识绝不来自用户、厂区或业务主键。
        var graph = "urn:ontology-platform:temporary:" + Guid.NewGuid().ToString("N");
        graphs.Add(graph);
        await SendAsync(validation, "data?graph=" + Uri.EscapeDataString(graph), HttpMethod.Put, source, "text/plain", token);
        return graph;
    }

    /// <summary>固定GSP读取有界完整RDF图。</summary>
    private async Task<RdfTriple[]> ReadGraphAsync(Uri origin, string graph, CancellationToken token) =>
        JenaRdfCodec.Parse(await SendAsync(origin, "data?graph=" + Uri.EscapeDataString(graph), HttpMethod.Get, null, "application/rdf+json", token));

    /// <summary>发送受控请求，响应体有硬上限且不传播Jena原始错误正文。</summary>
    private async Task<string> SendAsync(Uri origin, string path, HttpMethod method, string? body, string accept, CancellationToken token)
    {
        // 请求URI只能由已验证的dataset和固定操作构成。
        using var request = new HttpRequestMessage(method, new Uri(origin, path));
        request.Headers.Accept.ParseAdd(accept);
        if (body is not null) request.Content = new StringContent(body, Encoding.UTF8, "text/turtle");
        // 命名客户端没有自动重定向与非幂等重试。
        using var client = clients.CreateClient("ontology-jena");
        // 首先只读取响应头，避免自动缓冲无界响应。
        using var response = await client.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, token);
        if (method == HttpMethod.Delete && response.StatusCode == HttpStatusCode.NotFound) return "";
        if (!response.IsSuccessStatusCode) throw new SemanticOperationException(response.StatusCode == HttpStatusCode.BadRequest ? 422 : 503, response.StatusCode == HttpStatusCode.BadRequest ? "rdf_parse_invalid" : "semantic_unavailable");
        // 在流层计数，不能仅相信Content-Length。
        using var stream = await response.Content.ReadAsStreamAsync(token);
        // 临时字节存储上限8MiB，足以容纳5000个受限三元组的JSON展开。
        using var content = new MemoryStream();
        // 固定缓冲区避免按声明长度分配。
        var buffer = new byte[8192];
        // 当前读取长度用于准确累加响应字节预算。
        int count;
        while ((count = await stream.ReadAsync(buffer, token)) > 0)
        {
            if (content.Length + count > 8 * 1024 * 1024) throw new SemanticOperationException(422, "rdf_response_budget");
            content.Write(buffer, 0, count);
        }
        return Encoding.UTF8.GetString(content.ToArray());
    }

    /// <summary>配置只接受不含身份或查询的HTTP回环dataset。</summary>
    private static Uri Origin(string? value)
    {
        if (!Uri.TryCreate(value?.TrimEnd('/') + "/", UriKind.Absolute, out var origin) || origin.Scheme != "http" || !origin.IsLoopback || origin.UserInfo.Length != 0 || origin.Query.Length != 0 || origin.Fragment.Length != 0)
            throw new InvalidOperationException("语义运行时需要固定回环dataset配置。");
        return origin;
    }

    /// <summary>本轮发布图名唯一派生规则，不能由外部传入任意图IRI。</summary>
    private static void CheckGraphs(string releaseId, string ontology, string data)
    {
        if (!Guid.TryParseExact(releaseId, "N", out _) || ontology != "urn:ontology-platform:release:" + releaseId + ":ontology" || data != "urn:ontology-platform:release:" + releaseId + ":data")
            throw new SemanticOperationException(422, "release_graph_invalid");
    }

    /// <summary>发布清单必须绑定完整源散列及服务器派生图名。</summary>
    private static void CheckManifest(ReleaseManifest manifest, SourceBundle sources)
    {
        CheckGraphs(manifest.ReleaseId, manifest.OntologyGraphIri, manifest.DataGraphIri);
        if (manifest.Hashes != JenaRdfCodec.Hashes(sources)) throw new SemanticOperationException(409, "source_hash_conflict");
    }

    /// <summary>从标准报告逐结果映射定位字段，不将其写入普通日志。</summary>
    private static ValidationIssue[] Issues(RdfTriple[] report) => report
        .Where(triple => triple.Predicate == JenaRdfCodec.Type && triple.Object.Value == ShapePolicy.Sh + "ValidationResult")
        .Select(result => new ValidationIssue
        {
            Severity = Value(report, result.Subject, "resultSeverity")?.Value switch { ShapePolicy.Sh + "Info" => DiagnosticSeverity.Info, ShapePolicy.Sh + "Warning" => DiagnosticSeverity.Warning, _ => DiagnosticSeverity.Error },
            FocusNode = Value(report, result.Subject, "focusNode"),
            Path = Value(report, result.Subject, "resultPath")?.Value,
            Value = Value(report, result.Subject, "value"),
            SourceShape = Value(report, result.Subject, "sourceShape"),
            ConstraintComponent = Value(report, result.Subject, "sourceConstraintComponent")?.Value,
            Message = Value(report, result.Subject, "resultMessage")?.Value ?? "数据不满足已登记约束。",
            SourceId = "synthetic-data"
        }).ToArray();

    /// <summary>读取特定标准报告节点的指定谓词。</summary>
    private static RdfTerm? Value(RdfTriple[] report, RdfTerm subject, string predicate) => report.FirstOrDefault(triple => triple.Subject == subject && triple.Predicate == ShapePolicy.Sh + predicate)?.Object;

    /// <summary>明确标识未验证OWL公理及空白节点；保存和导出不丢失它们。</summary>
    private static SemanticDiagnostic[] Support(RdfTriple[] triples)
    {
        // 只列出已支持的OWL类/属性声明，未知公理保守阻断。
        var allowedOwl = new[] { "Class", "ObjectProperty", "DatatypeProperty", "NamedIndividual", "Ontology" }.Select(name => JenaRdfCodec.Owl + name).ToHashSet(StringComparer.Ordinal);
        return triples.Where(triple => triple.Subject.Kind == RdfTermKind.Blank || triple.Object.Kind == RdfTermKind.Blank ||
                triple.Predicate.StartsWith(JenaRdfCodec.Owl, StringComparison.Ordinal) ||
                (triple.Predicate.StartsWith("http://www.w3.org/2000/01/rdf-schema#", StringComparison.Ordinal) && !EditablePredicate(triple.Predicate, [])) ||
                (triple.Object.Kind == RdfTermKind.Iri && triple.Object.Value.StartsWith(JenaRdfCodec.Owl, StringComparison.Ordinal) && !allowedOwl.Contains(triple.Object.Value)))
            .Select(triple => new SemanticDiagnostic { Code = triple.Predicate == JenaRdfCodec.Owl + "imports" ? "import_unlocked" : "axiom_unsupported", Severity = DiagnosticSeverity.Error, Message = "源码已完整保留；此公理尚未支持结构编辑或发布，OWL逻辑推理未运行。", FocusNode = triple.Subject, Path = triple.Predicate }).ToArray();
    }

    /// <summary>编辑标准基本谓词或本图实际声明的对象/数据属性。</summary>
    private static bool EditablePredicate(string predicate, RdfTriple[] triples) =>
        new[] { JenaRdfCodec.Type, JenaRdfCodec.Label, "http://www.w3.org/2000/01/rdf-schema#comment", "http://www.w3.org/2000/01/rdf-schema#subClassOf", "http://www.w3.org/2000/01/rdf-schema#domain", "http://www.w3.org/2000/01/rdf-schema#range" }.Contains(predicate, StringComparer.Ordinal) ||
        triples.Any(triple => triple.Subject.Value == predicate && triple.Predicate == JenaRdfCodec.Type && triple.Object.Value is JenaRdfCodec.Owl + "ObjectProperty" or JenaRdfCodec.Owl + "DatatypeProperty");

    /// <summary>由实际图构建有界节点和边，完整RDF三元组仍保留。</summary>
    private static SemanticAnalysis Analysis(SourceBundle sources, long revision, RdfTriple[] triples)
    {
        // 散列始终取权威源UTF8，不取Jena重新序列化文本。
        var hashes = JenaRdfCodec.Hashes(sources);
        // 支持诊断决定结构编辑边界，不把未知项悄悄过滤掉。
        var diagnostics = Support(triples);
        // 所有有IRI主体的声明节点由真实类型和标签生成。
        var nodes = triples.Where(triple => triple.Subject.Kind == RdfTermKind.Iri).GroupBy(triple => triple.Subject.Value)
            .Select(group => new SemanticNode
            {
                Id = group.Key,
                Label = group.FirstOrDefault(triple => triple.Predicate == JenaRdfCodec.Label)?.Object.Value ?? group.Key,
                TypeIris = group.Where(triple => triple.Predicate == JenaRdfCodec.Type && triple.Object.Kind == RdfTermKind.Iri).Select(triple => triple.Object.Value).Distinct().ToArray(),
                Kind = group.Any(triple => triple.Predicate == JenaRdfCodec.Type && triple.Object.Value == JenaRdfCodec.Owl + "Class") ? SemanticNodeKind.Class : group.Any(triple => triple.Predicate == JenaRdfCodec.Type && triple.Object.Value == JenaRdfCodec.Owl + "ObjectProperty") ? SemanticNodeKind.ObjectProperty : group.Any(triple => triple.Predicate == JenaRdfCodec.Type && triple.Object.Value == JenaRdfCodec.Owl + "DatatypeProperty") ? SemanticNodeKind.DatatypeProperty : SemanticNodeKind.Individual
            }).ToArray();
        // 边仅来自IRI到IRI的真实三元组，ID基于规范单三元组散列。
        var edges = triples.Where(triple => triple.Subject.Kind == RdfTermKind.Iri && triple.Object.Kind == RdfTermKind.Iri)
            .Select(triple => new SemanticEdge { Id = OntologyRules.Hash(JenaRdfCodec.Triple(triple)), Source = triple.Subject.Value, PredicateIri = triple.Predicate, Target = triple.Object.Value, Label = triple.Predicate }).ToArray();
        if (nodes.Length > 1000 || edges.Length > 2000) throw new SemanticOperationException(422, "projection_budget");
        return new SemanticAnalysis { Hashes = hashes, Projection = new SemanticProjection { Revision = revision, Hashes = hashes, Triples = triples, Nodes = nodes, Edges = edges, StructuralEditAllowed = diagnostics.Length == 0, Diagnostics = diagnostics } };
    }
}
