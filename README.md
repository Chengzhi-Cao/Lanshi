# Lanshi 视频商店

本地后端版视频商店：展示预览图，单个视频 5 元，微信扫码付款后开放下载。

## 运行

```powershell
python .\Lanshi\server.py
```

打开终端里显示的本地地址，通常是：

```text
http://127.0.0.1:8000
```

## 本地微信收款码模式

默认 `WECHAT_PAY_MODE=manual`。服务器会优先读取：

```text
Lanshi/pay.jpg
```

如果这里没有，则读取视频素材目录下的：

```text
pay.jpg
```

用户购买单个视频时会看到这张微信收款码。付款后，卖家打开本地后台确认收款，订单会变为已支付，买家页面会自动出现下载按钮。

卖家后台地址：

```text
http://127.0.0.1:8000/admin.html
```

默认卖家确认码：

```text
lanshi-local-admin
```

可以用环境变量修改：

```text
LANSHI_ADMIN_TOKEN=你的确认码
```

这个模式适合本地试运营和人工确认收款。固定收款码不能自动验证微信到账，也不能直接用于公开上线。

## 接入正式微信支付

正式上线需要微信商户号、HTTPS、公网回调地址，以及回调验签和通知解密。环境变量示例：

```text
WECHAT_PAY_MODE=wechat
WECHAT_APPID=
WECHAT_MCHID=
WECHAT_SERIAL_NO=
WECHAT_PRIVATE_KEY_PATH=
WECHAT_NOTIFY_URL=
```

当前后端已经保留 Native 下单结构和通知入口，但生产环境前仍需要补齐微信支付回调验签、资源解密、订单状态幂等更新和后台对账。

## 数据

订单和购买记录保存在：

```text
Lanshi/data/lanshi_store.db
```
