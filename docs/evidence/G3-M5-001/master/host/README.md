# E0-P0 实测窗口与边界

用户在本会话确认自行开启“显示器关闭时防止自动睡眠”；实测AC sleep=0/displaysleep=10，Codex未写全局电源配置。3分钟锁屏37心跳，以及后续60秒13心跳均连续；后者每次同时读取IOConsoleLocked=true和外接显示器asleep=true，电源日志同窗0条Sleep/Wake，最大间隔5076ms。

外接状态仅用Apple官方只读CoreGraphics CGGetOnlineDisplayList/CGDisplayIsAsleep/CGDisplayIsBuiltin，只保存外接数量和布尔值，不截图/读取应用/显示器身份。来源：[Apple显示睡眠API](https://developer.apple.com/documentation/coregraphics/cgdisplayisasleep(_:))、[Apple在线显示器](https://developer.apple.com/documentation/coregraphics/cggetonlinedisplaylist(_:_:_:))。本机真实读取成功，非模拟测试。

本结果通过宿主最低开工门禁，正式整会话保障依用户已开启的系统策略及任务有界监测，不依赖短命令caffeinate。主监测PID6932、最长43200秒；当前仍进行中，最终整会话窗口/政策变化/睡眠统计和精确终止结果必须后置核实，不能用此短窗宣称整夜PASS。任务级fixture只证明本进程准确PID的-i/-s断言存在及正常/主动终止释放；不代表桌面App全寿命。无-d/-u、无sudo/pmset写入、无登录项、无全局killall。电源中断/主动Sleep/重启不属idle sleep保证。
