using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace OntologyPlatform.Modules.Connections;

/// <summary>仅合成环境的AEAD凭据保险箱，KEK来自受控文件，不使用环境值或硬编码回退。</summary>
public sealed class ConnectionSecretCipher : IDisposable
{
    /// <summary>独立挂载的256位密钥，仅存于当前服务进程。</summary>
    private readonly byte[] key;

    /// <summary>读取准确Secret文件，缺失或长度错误即失败关闭。</summary>
    public ConnectionSecretCipher(string keyPath)
    {
        key = File.ReadAllBytes(keyPath);
        if (key.Length != 32) throw new InvalidOperationException("Connection key unavailable.");
    }

    /// <summary>将明文加密到指定记录，AAD绑定主体、范围、用途、引用及版本。</summary>
    public void Encrypt(ConnectionSecretRecord record, string value)
    {
        // 每次加密独立随机nonce，避免相同KEK下重用。
        var nonce = RandomNumberGenerator.GetBytes(12);
        // 明文字节只在加密调用期间存在，finally擦除缓冲区。
        var plain = Encoding.UTF8.GetBytes(value);
        // GCM密文长度与明文字节一致，认证标签固定128位。
        var cipher = new byte[plain.Length];
        // 标签不携可逆明文，仍不进入公开响应或日志。
        var tag = new byte[16];
        try
        {
            using var aes = new AesGcm(key, 16);
            aes.Encrypt(nonce, plain, cipher, tag, Aad(record));
            record.Nonce = Convert.ToBase64String(nonce);
            record.Ciphertext = Convert.ToBase64String(cipher);
            record.Tag = Convert.ToBase64String(tag);
        }
        finally
        {
            CryptographicOperations.ZeroMemory(plain);
        }
    }

    /// <summary>只有同一绑定身份与版本可解密；完整性错误不泄露密文或路径。</summary>
    public string Decrypt(ConnectionSecretRecord record)
    {
        // 解密结果在本调用之后只交给受控Adapter，绝不序列化返回。
        var plain = new byte[Convert.FromBase64String(record.Ciphertext).Length];
        try
        {
            using var aes = new AesGcm(key, 16);
            aes.Decrypt(Convert.FromBase64String(record.Nonce), Convert.FromBase64String(record.Ciphertext), Convert.FromBase64String(record.Tag), plain, Aad(record));
            return Encoding.UTF8.GetString(plain);
        }
        catch (CryptographicException)
        {
            throw new InvalidOperationException("Connection secret unavailable.");
        }
        finally
        {
            CryptographicOperations.ZeroMemory(plain);
        }
    }

    /// <summary>用途隔离HMAC绑定完整请求，低熵密码不能通过裸SHA猜测。</summary>
    public string RequestHash(string request) => Convert.ToHexStringLower(HMACSHA256.HashData(key, Encoding.UTF8.GetBytes("connection-request-v1:" + request)));

    /// <summary>构造无歧义的完整AEAD关联数据。</summary>
    private static byte[] Aad(ConnectionSecretRecord record) => JsonSerializer.SerializeToUtf8Bytes(new
    {
        record.Id,
        record.Owner,
        record.OrganizationId,
        Sites = record.SiteIds.Order(StringComparer.Ordinal).ToArray(),
        record.Purpose,
        record.Version,
        record.KeyVersion
    });

    /// <summary>服务停止时擦除当前进程拥有的KEK缓冲区。</summary>
    public void Dispose() => CryptographicOperations.ZeroMemory(key);
}
