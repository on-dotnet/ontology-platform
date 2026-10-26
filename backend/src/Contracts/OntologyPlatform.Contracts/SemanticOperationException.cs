namespace OntologyPlatform.Contracts;

/// <summary>表示可安全映射为固定Problem的业务边界拒绝，不携带源码或原始异常。</summary>
public sealed class SemanticOperationException : Exception
{
    /// <summary>构造固定状态与机器代码，调用方只能传入预先登记的常量。</summary>
    /// <param name="status">HTTP映射所需的明确状态。</param>
    /// <param name="code">固定机器错误代码，不能拼接输入。</param>
    public SemanticOperationException(int status, string code) : base("语义操作未满足受控合同。")
    {
        Status = status;
        Code = code;
    }

    /// <summary>外层传输适配所需状态，不由客户端值决定。</summary>
    public int Status { get; }

    /// <summary>受控机器错误代码，不包含用户输入。</summary>
    public string Code { get; }
}
