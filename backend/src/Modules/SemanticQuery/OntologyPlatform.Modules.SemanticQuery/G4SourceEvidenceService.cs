using System.Globalization;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.SemanticQuery;

/// <summary>读取回执与业务证据的持久交叉引用边界，不向业务消费者暴露完整内部Binding。</summary>
public static class G4SourceEvidenceService
{
    /// <summary>只有已闭合且与同一查询固定版本一致的回执才能同结果原子保存。</summary>
    public static G4QueryState BindReceipts(string queryId, G4QueryState state, G4QueryResultV1 result, G4QueryStoredReceipt[] receipts)
    {
        if (receipts.Length != result.SubSources.Count(item => item.SourceReadReceiptId is not null) || receipts.Length > 100
            || receipts.Select(item => item.Receipt.ReceiptId).Distinct(StringComparer.Ordinal).Count() != receipts.Length)
            throw Invalid();
        foreach (var stored in receipts)
        {
            // 回执摘要置于外列，规范字节不包含摘要自身。
            var receipt = stored.Receipt;
            // 一分支一回执且每个结果分支必须唯一对应，不能重复借用成功读取。
            var branch = result.SubSources.SingleOrDefault(item => item.SourceReadReceiptId == receipt.ReceiptId);
            if (receipt.SchemaVersion != "g4.read-receipt.v1" || receipt.QueryId != queryId || receipt.Binding != state.Binding
                || stored.ReceiptHash != G4QueryCanonical.Hash(G4QueryCanonical.Serialize(receipt))
                || branch is null || branch.ConnectionId != state.Binding.ConnectionId || branch.Status != receipt.Status
                || branch.WatermarkKind != receipt.WatermarkKind || branch.Limited != receipt.Limited
                || branch.ObservedAtUtc != receipt.ReadCompletedAtUtc || receipt.TraceId != result.TraceId
                || receipt.Scope.OrganizationId != state.Scope.OrganizationId
                || !receipt.Scope.SiteIds.Order(StringComparer.Ordinal).SequenceEqual(state.Scope.SiteIds.Order(StringComparer.Ordinal))
                || receipt.RowCount is < 0 or > 100 || !Hex(receipt.QueryPlanHash) || receipt.AdapterVersion != "pg-query-v1"
                || string.IsNullOrWhiteSpace(receipt.SourceDatasetRef) || receipt.SourceDatasetRef.Length > 4096
                || receipt.Watermark?.Length > 256 || receipt.Precision is not ("RECORD" or "ROW_KEY" or "DATASET" or "TIME_WINDOW" or "UNKNOWN"))
                throw Invalid();
            // 时间必须是真实有序UTC词法，不能把失败写成读取未来窗口。
            var started = Time(receipt.ReadStartedAtUtc);
            // 结束时间沿用源事务完成事实，精度与规范结果相同。
            var completed = Time(receipt.ReadCompletedAtUtc);
            if (completed < started || receipt.Status is "SUCCESS" or "EMPTY" && !Hex(receipt.ResultHash)
                || receipt.Status == "EMPTY" && (receipt.RowCount != 0 || receipt.Limited)
                || receipt.Status is not ("SUCCESS" or "EMPTY") && (receipt.RowCount != 0 || receipt.ResultHash is not null)
                || receipt.WatermarkKind == "UNKNOWN" && receipt.Watermark is not null
                || receipt.WatermarkKind == "TRANSACTION_SNAPSHOT" && string.IsNullOrWhiteSpace(receipt.Watermark)
                || receipt.SourceRecordRef is not null && (receipt.RowCount != 1 || receipt.Precision is not ("RECORD" or "ROW_KEY")))
                throw Invalid();
        }
        foreach (var evidence in result.Evidence)
        {
            // 证据存在性不足以证明来源，必须同分支回执、原目录及固定发布闭合。
            var receipt = receipts.SingleOrDefault(item => item.Receipt.ReceiptId == evidence.SourceReadReceiptId)?.Receipt ?? throw Invalid();
            if (receipt.Status != "SUCCESS" || evidence.SourceDatasetRef != receipt.SourceDatasetRef
                || evidence.ConnectionId != receipt.Binding.ConnectionId || evidence.MappingReleaseId != receipt.Binding.MappingReleaseId
                || evidence.SourceCatalogSnapshotId != receipt.Binding.OriginalCatalogSnapshotId || evidence.ObservedAtUtc != receipt.ReadCompletedAtUtc
                || evidence.Scope.OrganizationId != receipt.Scope.OrganizationId || !evidence.Scope.SiteIds.All(receipt.Scope.SiteIds.Contains)
                || !SupportsPrecision(receipt.Precision, evidence.Precision))
                throw Invalid();
        }
        return state with { Receipts = receipts };
    }

    /// <summary>证据最多沿用回执能证明的精度；降低精度可以，未知不能升级成记录定位。</summary>
    private static bool SupportsPrecision(string receipt, string evidence) => receipt switch
    {
        "RECORD" or "ROW_KEY" => evidence is "RECORD" or "ROW_KEY" or "DATASET" or "TIME_WINDOW" or "UNKNOWN",
        "TIME_WINDOW" => evidence is "TIME_WINDOW" or "DATASET" or "UNKNOWN",
        "DATASET" => evidence is "DATASET" or "UNKNOWN",
        "UNKNOWN" => evidence == "UNKNOWN",
        _ => false
    };

    /// <summary>回执散列使用固定小写hex，不接受任意长度身份。</summary>
    private static bool Hex(string? value) => value is { Length: 64 } && value.All(char.IsAsciiHexDigitLower);

    /// <summary>真实PG读取时间统一保留微秒，不接受本地时区或宽松解析。</summary>
    private static DateTimeOffset Time(string value) => DateTimeOffset.TryParseExact(value, "yyyy-MM-dd'T'HH:mm:ss.ffffff'Z'",
        CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal, out var time) ? time : throw Invalid();

    /// <summary>对外只提供固定错误码，不披露失败回执或内部版本字段。</summary>
    private static SemanticOperationException Invalid() => new(503, "query_result_invalid");
}
