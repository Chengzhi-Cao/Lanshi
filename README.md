# Lanshi 视频商店

这是一个不用 Python 服务也能预览的静态版页面。

## 直接预览

双击打开：

```text
Lanshi/index.html
```

页面会读取 `catalog.js` 里的视频清单，展示封面、片名、系列、大小、价格、微信支付弹窗和前端解锁演示。

## 更新视频清单

如果素材文件夹里新增或删除视频，运行：

```powershell
.\Lanshi\tools\make-catalog.ps1
```

## 生成更多封面

当前页面没有封面的条目会显示标题占位。要生成更多封面：

```powershell
.\Lanshi\tools\make-thumbnails.ps1 -Limit 120
```

把 `-Limit 0` 改成全量生成。

## 正式上线说明

静态页面只能做展示和流程预览，不能真正保护视频文件。真实微信收款、订单校验、支付回调、登录和防盗链都需要服务端。
