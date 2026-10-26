using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.Publishing;

/// <summary>模块内部确定性绑定及应用授权，不复制跨模块DTO。</summary>
internal static class PublishingRules
{
    /// <summary>计算精确UTF8字节散列。</summary>
    internal static string Hash(string value) => Hash(Encoding.UTF8.GetBytes(value));

    /// <summary>计算二进制不可变对象散列。</summary>
    internal static string Hash(ReadOnlySpan<byte> value) => Convert.ToHexStringLower(SHA256.HashData(value));

    /// <summary>完整范围必须同组织且每个厂区都获准。</summary>
    internal static bool Covers(ActorContext actor, ResourceScope scope) => scope.SiteIds.Length is >= 1 and <= 16 && scope.OrganizationId == actor.OrganizationId && scope.SiteIds.All(site => actor.SiteIds.Contains(site, StringComparer.Ordinal));

    /// <summary>应用层再次拒绝越界，独立于HTTP路由。</summary>
    internal static void DemandScope(ActorContext actor, ResourceScope scope)
    {
        if (!Covers(actor, scope)) throw new SemanticOperationException(403, "scope_denied");
    }

    /// <summary>写角色为完整operator，审核为完整auditor，读角色沿用G1。</summary>
    internal static void DemandRole(ActorContext actor, string? required = null)
    {
        if (string.IsNullOrWhiteSpace(actor.SubjectId) || (required is null ? !actor.Roles.Any(role => role is "platform.viewer" or "platform.operator" or "platform.auditor") : !actor.Roles.Contains(required, StringComparer.Ordinal))) throw new SemanticOperationException(403, "role_denied");
    }

    /// <summary>即使非HTTP调用也检查受控命令预算。</summary>
    internal static void Command(CommandContext command)
    {
        if (command is null || string.IsNullOrWhiteSpace(command.CommandId) || command.CommandId.Length > 64 || string.IsNullOrWhiteSpace(command.IdempotencyKey) || command.IdempotencyKey.Length > 64 || string.IsNullOrWhiteSpace(command.Reason) || command.Reason.Length > 500 || command.ExpectedRevision < 0) throw new SemanticOperationException(422, "command_invalid");
    }

    /// <summary>规范完整范围和操作共同构成幂等空间，不使用首厂。</summary>
    internal static string Key(ResourceScope scope, string operation, string key) => Hash(JsonSerializer.Serialize(new { scope = scope with { SiteIds = scope.SiteIds.Distinct(StringComparer.Ordinal).Order(StringComparer.Ordinal).ToArray() }, operation, key }));

    /// <summary>审核绑定只取不可变提案内容，排除审核本身和状态避免循环。</summary>
    internal static string Binding(ReleaseProposal proposal) => Hash(JsonSerializer.Serialize(new { proposal.ProposalId, proposal.Kind, proposal.AssetId, proposal.Scope, proposal.DraftId, proposal.DraftRevision, proposal.Hashes, proposal.ValidationReportId, proposal.TargetReleaseId, proposal.TargetManifestHash, proposal.SubmittedBy, proposal.SubmittedAtUtc, proposal.ExpiresAtUtc }));
}
