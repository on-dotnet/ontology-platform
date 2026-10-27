# 兼容验收器零执行纠偏

首次独立二进制读真实V2时MTP改变工作目录，fixture找不到制品而Inconclusive。默认allow-skipped退出0，初版驱动误报PASS；该结论撤回，原JSON/log保留invalidated文件。修正为相对保留二进制位置读取公开制品，驱动强制zero-tests-policy strict和minimum-expected-tests 1。原二进制不覆盖，新保留reader-v2并在正式AppHost/V2写入前验证。不是产品兼容通过证据。
