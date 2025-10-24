# NodeSeek和DeepFlood的自动签到脚本

NodeSeek和DeepFlood的自动签到青龙脚本，签到模式默认为随机签到，帮助用户轻松获取论坛每日"鸡腿"奖励


## 依赖安装

依赖管理 - Python3 - 创建依赖
+ curl_cffi
+ python-dotenv
+ urllib3


## 特性

- **双站点支持** - 同时支持 NodeSeek 和 DeepFlood 论坛
- **智能登录** - 支持Cookie登录签到和账号密码自动登录
- **自动续期** - Cookie失效时自动通过账号密码登录更新
- **验证码绕过** - 集成CloudFlare Turnstile验证码解决服务
- **多账户管理** - 每个站点支持无限个账户
- **智能通知** - 每天只发送一次汇总通知，告别通知轰炸
- **签到统计** - 自动统计近30天签到收益

## 青龙面板部署

### 拉取仓库

```bash
ql repo https://github.com/awinds/ns_df_sign.git
```

### Docker部署CloudFreed服务

```bash
docker run -itd \
  --name cloudflyer \
  -p 3000:3000 \
  --restart unless-stopped \
  jackzzs/cloudflyer \
  -K 你的客户端密钥 \
  -H 0.0.0.0
```

或使用`docker-compose.yml`
```
version: "3"
services:
  cloudflyer:
    image: jackzzs/cloudflyer
    container_name: cloudflyer
    ports:
      - 3000:3000
    restart: unless-stopped
    command: >
      -K "你的客户端密钥" 
      -H "0.0.0.0"
```

```bash
docker-compose up -d
```

验证服务
```bash
# 检查容器运行状态
docker ps | grep cloudflyer

# 测试服务连通性
curl http://你的服务器IP:3000/health
```

### 环境变量

| 变量名称 | 必要性 | 说明 |
| :------: | :----: | :--- |
| `NS_COOKIE` | cookie登录 | NodeSeek 论坛的用户 Cookie，可在浏览器开发者工具(F12)的网络请求中获取，多账号用`&`或换行符分隔 |
| `DF_COOKIE` | cookie登录 | DeepFlood 论坛的用户 Cookie，可在浏览器开发者工具(F12)的网络请求中获取，多账号用`&`或换行符分隔 |
| `NS_USER` | 建议 | NodeSeek 论坛用户名，无Cookie时使用用户名和密码登录并自动更新 Cookie，多账号用`&`分隔 |
| `NS_PASS` | 建议 | NodeSeek 论坛密码，无Cookie时使用用户名和密码登录并自动更新 Cookie，多账号用`&`分隔，和`NS_USER`对应 |
| `DF_USER` | 建议 | DeepFlood 论坛用户名，无Cookie时使用用户名和密码登录并自动更新 Cookie，多账号用`&`分隔 |
| `DF_PASS` | 建议 | DeepFlood 论坛密码，无Cookie时使用用户名和密码登录并自动更新 Cookie，多账号用`&`分隔，和`DF_USER`对应 |
| `CLOUDFLYER_API_URL` | 用户名登录必填 | 部署CloudFreed服务后的服务地址，如http://你的服务器IP:3000 |
| `CLOUDFLYER_CLIENTT_KEY` | 用户名登录必填 | 部署CloudFreed服务后的客户端密钥 |
| `TG_BOT_TOKEN` | 可选 | Telegram 机器人的 Token，用于通知签到结果 |
| `TG_USER_ID` | 可选 | Telegram 用户ID或ChatID，用于接收通知 |
| `NS_RANDOM` | 可选 | 随机参数，默认true |


### 定时任务

```bash
30 8 * * * task awinds_ns_df_sign/auto-sign.py
```

```bash
30 8 * * * python3 /ql/scripts/ns_df_sign/auto-sign.py
```


## 免责声明

本项目仅供学习交流使用，请遵守 NodeSeek 和 DeepFlood 论坛的相关规定和条款。
感谢 [NodeSeek](https://www.nodeseek.com) 和 [DeepFlood](https://www.deepflood.com) 提供优质的技术社区
