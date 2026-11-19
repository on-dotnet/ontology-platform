using OntologyPlatform.Contracts;

namespace OntologyPlatform.G2ContractTests;

/// <summary>入口、Gateway 与外层绑定共享同一次期限，物理确认不能误放后续连接。</summary>
[TestClass]
public sealed class G4ExecutionScopeTests
{
    /// <summary>Gateway 已退出时，MCP 绑定仍观察同一较短绝对时刻与取消令牌。</summary>
    [TestMethod]
    public void NestedTighteningSurvivesGatewayExit()
    {
        using var outer = new G4RequestDeadline(TimeProvider.System, CancellationToken.None);
        // 先记录入口的原始五秒截止，再在真实嵌套范围内收紧。
        var initial = outer.DeadlineUtc;
        using (var inner = new G4RequestDeadline(TimeProvider.System, outer.Token))
        {
            inner.Tighten(750);
            Assert.AreEqual(initial.AddMilliseconds(-4250), inner.DeadlineUtc);
            Assert.AreEqual(inner.DeadlineUtc, SemanticReadDeadline.Current);
        }
        Assert.AreSame(outer, G4RequestDeadline.Current);
        Assert.AreEqual(initial.AddMilliseconds(-4250), outer.DeadlineUtc);
        outer.Tighten(0);
        Assert.IsTrue(outer.Token.IsCancellationRequested);
    }

    /// <summary>已释放连接的旧凭据不能确认新一物理申请。</summary>
    [TestMethod]
    public void LateConfirmationCannotReleaseNextPhysicalAcquisition()
    {
        using var scope = new G4OracleSourceLifetime("synthetic-query");
        Assert.IsTrue(scope.CleanupConfirmed);
        var first = scope.BeginSource();
        Assert.IsFalse(scope.CleanupConfirmed);
        Assert.ThrowsExactly<InvalidOperationException>(() => scope.BeginSource());
        scope.ConfirmReleased(first);
        var second = scope.BeginSource();
        Assert.ThrowsExactly<InvalidOperationException>(() => scope.ConfirmReleased(first));
        Assert.IsFalse(scope.CleanupConfirmed);
        scope.ConfirmReleased(second);
        Assert.IsTrue(scope.CleanupConfirmed);
    }
}
