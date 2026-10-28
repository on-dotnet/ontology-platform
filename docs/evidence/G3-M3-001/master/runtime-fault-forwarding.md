# M3完整入口故障注入开关

M3受控AppHost orchestration新增--smoke-fault-check，传到真实full-g2-e2e.py及Node browser smoke。新增测试走完整upper/downstream argparse和实际子进程退出记录；RED因为upper不识别flag，GREEN16tests通过。该命令只控制既有隐藏canvas快速FAIL/恢复PASS，不改变产品默认source。控制面fixture不代表真实浏览器已执行；待新canonical可用后实际完整命令为python3 scripts/acceptance/g3-acceptance-runtime.py --start-runtime --milestone M3 --smoke-fault-check。

两个新维护测试FusekiTransfer17/OwnedTestContainers12已接永久SelfTest，artifact仍默认BLOCKED。
