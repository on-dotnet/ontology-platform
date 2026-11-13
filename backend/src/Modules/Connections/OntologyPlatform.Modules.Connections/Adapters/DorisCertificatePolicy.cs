using System.Net.Security;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;

namespace OntologyPlatform.Modules.Connections;

/// <summary>Doris实际TLS握手的严格私有CA验证策略，不修改全局信任。</summary>
internal static class DorisCertificatePolicy
{
    /// <summary>在当前实际TLS握手回调中校验完整叶证书链、名称和用途。</summary>
    /// <param name="certificate">当前服务端实际呈现的证书。</param>
    /// <param name="presentedChain">系统握手获得的链，仅提供中间证书。</param>
    /// <param name="errors">系统基于固定TargetHost得到的名称与缺证书错误。</param>
    /// <param name="caPath">服务端配置的本任务私有CA公证书路径。</param>
    /// <returns>仅在全部本地验证通过时返回真。</returns>
    internal static bool Validate(X509Certificate? certificate, X509Chain? presentedChain, SslPolicyErrors errors, string caPath)
    {
        if (certificate is null || presentedChain is null || presentedChain.ChainElements.Count > 16
            || errors is not (SslPolicyErrors.None or SslPolicyErrors.RemoteCertificateChainErrors)) return false;
        try
        {
            // 独立拥有证书副本，不释放TLS流持有的证书。
            using var leaf = X509CertificateLoader.LoadCertificate(certificate.GetRawCertData());
            // 根信任只来自显式私有文件，绝不修改系统信任。
            using var root = X509Certificate2.CreateFromPem(File.ReadAllText(caPath));
            // 当前时间只读系统时钟，不允许忽略有效期。
            var now = DateTime.UtcNow;
            if (now < leaf.NotBefore.ToUniversalTime() || now > leaf.NotAfter.ToUniversalTime()
                || now < root.NotBefore.ToUniversalTime() || now > root.NotAfter.ToUniversalTime()) return false;
            // 为实际叶证书建立独立且不忽略任何错误的验证链。
            using var chain = new X509Chain();
            chain.ChainPolicy.TrustMode = X509ChainTrustMode.CustomRootTrust;
            chain.ChainPolicy.CustomTrustStore.Add(root);
            chain.ChainPolicy.VerificationFlags = X509VerificationFlags.NoFlag;
            chain.ChainPolicy.ApplicationPolicy.Add(new Oid("1.3.6.1.5.5.7.3.1"));
            chain.ChainPolicy.DisableCertificateDownloads = true;
            // 本机合成CA无CRL/OCSP；明确不宣称在线撤销检查，禁止隐式外联。
            chain.ChainPolicy.RevocationMode = X509RevocationMode.NoCheck;
            // 系统提供的链仅贡献中间证书，不扩充自定义根信任。
            for (var index = 1; index < presentedChain.ChainElements.Count; index++) chain.ChainPolicy.ExtraStore.Add(presentedChain.ChainElements[index].Certificate);
            return chain.Build(leaf) && chain.ChainStatus.Length == 0;
        }
        catch (CryptographicException) { return false; }
        catch (IOException) { return false; }
        catch (UnauthorizedAccessException) { return false; }
    }
}
