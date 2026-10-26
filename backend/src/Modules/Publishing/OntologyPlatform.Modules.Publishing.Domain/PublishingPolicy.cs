namespace OntologyPlatform.Modules.Publishing.Domain;

/// <summary>不依赖外部服务的纯发布授权规则。</summary>
public static class PublishingPolicy
{
    /// <summary>判断是否满足异人完整审核角色及有效期。</summary>
    public static bool CanApprove(string subject, string[] roles, string submitter, DateTimeOffset now, DateTimeOffset expires) =>
        !string.IsNullOrWhiteSpace(subject) && subject != submitter
        && roles.Contains("platform.auditor", StringComparer.Ordinal) && now < expires;
}
