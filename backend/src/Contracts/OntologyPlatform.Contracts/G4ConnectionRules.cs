using System.Text.RegularExpressions;

namespace OntologyPlatform.Contracts;

/// <summary>M1所有传输入口复用的字段规则；资源授权和源端策略仍由应用服务核实。</summary>
public static class G4ConnectionRules
{
    /// <summary>验证严格反序列化之后的命令语义，未知请求类型拒绝。</summary>
    /// <param name="request">本轮登记的公共请求。</param>
    public static void Validate(object request)
    {
        switch (request)
        {
            case ConnectionCreateRequest create:
                Command(create.Command, true);
                Scope(create.ScopeSelection);
                Config(create.Config);
                Require(Text(create.DisplayName, 128));
                Require(create.Config is WebApiConnectionConfig { Profile.Authentication: "NONE" }
                    ? create.SecretRef is null : Text(create.SecretRef, 128));
                break;
            case ConnectionPatchRequest patch:
                Command(patch.Command, false);
                Require(patch.DisplayName is not null || patch.ScopeSelection is not null || patch.Config is not null);
                if (patch.DisplayName is not null) Require(Text(patch.DisplayName, 128));
                if (patch.ScopeSelection is not null) Scope(patch.ScopeSelection);
                if (patch.Config is not null) Config(patch.Config);
                break;
            case ConnectionSecretIntakeRequest secret:
                Command(secret.Command, true);
                Scope(secret.ScopeSelection);
                Require(secret.SecretValue is { Length: >= 8 and <= 4096 } && secret.Purpose is "POSTGRESQL_READONLY" or "WEB_API_KEY" or "DORIS_READONLY" or "ORACLE_READONLY");
                break;
            case ConnectionDraftProbeRequest probe:
                Command(probe.Command, true);
                Scope(probe.ScopeSelection);
                Config(probe.Config);
                Require(Text(probe.SecretRef, 128));
                break;
            case ConnectionRotateSecretRequest rotate:
                Command(rotate.Command, false);
                Require(Text(rotate.SecretRef, 128));
                break;
            case ConnectionMutationCommand mutation:
                Command(mutation.Command, false);
                break;
            default:
                throw new SemanticOperationException(422, "connection_profile_invalid");
        }
    }

    /// <summary>验证五类型配置的精确字段值，非PG配置不代表适配器已实现。</summary>
    /// <param name="config">唯一配置判别分支。</param>
    public static void Config(ConnectionConfig config)
    {
        switch (config)
        {
            case PgConnectionConfig { Profile: not null } pg:
                Require(Host(pg.Profile.Host) && Port(pg.Profile.Port) && Text(pg.Profile.Database, 63)
                    && Text(pg.Profile.Username, 63) && pg.Profile.SslMode is "VerifyFull" or "VerifyCA" or "Require"
                    && Names(pg.Profile.AllowedSchemas));
                break;
            case OracleConnectionConfig { Profile: not null } oracle:
                Require(Host(oracle.Profile.Host) && Port(oracle.Profile.Port) && Text(oracle.Profile.ServiceName, 128)
                    && Text(oracle.Profile.Username, 63) && Names(oracle.Profile.AllowedOwners) && oracle.Profile.Tls);
                break;
            case DorisConnectionConfig { Profile: not null } doris:
                Require(Host(doris.Profile.FeHost) && Port(doris.Profile.QueryPort) && Text(doris.Profile.Catalog, 128)
                    && Text(doris.Profile.Database, 63) && Text(doris.Profile.Username, 63) && doris.Profile.Tls);
                break;
            case TdengineConnectionConfig { Profile: not null } td:
                // 仅解析配置预览的URI，不向目标发送网络请求。
                Require(Uri.TryCreate(td.Profile.WsUrl, UriKind.Absolute, out var endpoint)
                    && endpoint.Scheme is "ws" or "wss" && string.IsNullOrEmpty(endpoint.UserInfo)
                    && Text(td.Profile.Database, 63) && td.Profile.TimePrecision is "MILLISECOND" or "MICROSECOND" or "NANOSECOND" or "UNKNOWN"
                    && (td.Profile.TimeZone is null || Text(td.Profile.TimeZone, 128)));
                break;
            case WebApiConnectionConfig { Profile: not null } web:
                // 解析批准源站的语法，不授予运行或外联能力。
                Require(Uri.TryCreate(web.Profile.BaseOrigin, UriKind.Absolute, out var origin)
                    && origin.Scheme == "https" && string.IsNullOrEmpty(origin.UserInfo)
                    && origin.GetLeftPart(UriPartial.Authority) == web.Profile.BaseOrigin
                    && Text(web.Profile.OperationId, 128) && web.Profile.Method == "GET"
                    && Text(web.Profile.ApprovedPath, 512) && web.Profile.ApprovedPath.StartsWith('/')
                    && !web.Profile.ApprovedPath.StartsWith("//", StringComparison.Ordinal)
                    && web.Profile.Authentication is "NONE" or "API_KEY_REF" or "OAUTH_CLIENT_CREDENTIALS_REF"
                    && web.Profile.Pagination is "NONE" or "PAGE" or "OFFSET" or "CURSOR" or "LINK"
                    && Text(web.Profile.HostPolicyRef, 128));
                break;
            default:
                throw new SemanticOperationException(422, "connection_profile_invalid");
        }
    }

    /// <summary>要求组织厂区结构完整；是否属于可信Actor另由应用服务检查。</summary>
    /// <param name="scope">请求或资源的完整范围。</param>
    public static void Scope(ResourceScope scope)
    {
        Require(scope is not null && Text(scope.OrganizationId, 128) && scope.SiteIds is { Length: >= 1 and <= 16 }
            && scope.SiteIds.All(site => Text(site, 128)) && scope.SiteIds.Distinct(StringComparer.Ordinal).Count() == scope.SiteIds.Length);
    }

    /// <summary>创建严格零修订，变更严格正修订且命令标识有界。</summary>
    /// <param name="command">冻结的G2命令四字段。</param>
    /// <param name="create">是否为创建命令。</param>
    private static void Command(CommandContext command, bool create)
    {
        Require(command is not null && Text(command.CommandId, 64) && Text(command.IdempotencyKey, 64)
            && Text(command.Reason, 500) && (create ? command.ExpectedRevision == 0 : command.ExpectedRevision >= 1));
    }

    /// <summary>拒绝空白、控制字符及超过预算的输入。</summary>
    private static bool Text(string? value, int maximum) => !string.IsNullOrWhiteSpace(value)
        && value.Length <= maximum && !value.Any(char.IsControl);

    /// <summary>受控主机字段不接受URL、连接串或多目标。</summary>
    private static bool Host(string? value) => Text(value, 253) && Regex.IsMatch(value!, "^[A-Za-z0-9][A-Za-z0-9.-]*$", RegexOptions.CultureInvariant);

    /// <summary>TCP端口严格限制合法整数范围。</summary>
    private static bool Port(int value) => value is >= 1 and <= 65535;

    /// <summary>M1标识符安全子集，防止未经审核引号或SQL片段进入适配器。</summary>
    private static bool Names(string[]? values) => values is { Length: >= 1 and <= 16 }
        && values.All(value => value is not null && Regex.IsMatch(value, "^[A-Za-z_][A-Za-z0-9_]{0,62}$", RegexOptions.CultureInvariant))
        && values.Distinct(StringComparer.Ordinal).Count() == values.Length;

    /// <summary>只抛固定安全错误，不把不可信值附到异常。</summary>
    private static void Require(bool condition)
    {
        if (!condition) throw new SemanticOperationException(422, "connection_profile_invalid");
    }
}
