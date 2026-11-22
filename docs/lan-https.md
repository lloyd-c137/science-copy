# 用局域网 IP 搭建开题手记试教站

一台电脑开网站，其他师生用浏览器访问它的局域网 IP。下面以 Windows 部署电脑为例，需要两台电脑在校园网内能互相访问。

**要跨电脑使用 Research Coach 插件，就需要 HTTPS。** 部署电脑提供网站证书，每台体验电脑导入一次试教站的根证书，让浏览器和插件都信任这个地址。本机演示可以继续用 `http://127.0.0.1:8767`。局域网只看网页、体验手工操作时，也可以不开 HTTPS，用 `--host` 绑定局域网 IP、用 `--no-demo` 和独立账号启动，省略插件参数。

## 1. 查 IP，启动试教网站

在部署电脑打开 PowerShell，运行 `ipconfig`。找到正在用的 Wi-Fi 或网线对应的 IPv4 地址。下面用 `192.168.1.23` 举例，操作时换成你查到的地址。

在仓库根目录用 [运行说明](../proposal_app/README.md#连接-codex)里的 `classroom.py` 命令创建师生账号，数据库路径用 `proposal_app/local_data/classroom.sqlite3`。至少建一个学生和一个老师。第一次登录老师账号后，在老师工作台点「发布活动」，选中参加试教的学生。

把同一个访问地址写进插件包和网站配置。以下命令在 Windows x64 上用 CPython 3.12 执行。用到哪种系统的插件，就构建对应的包。启动命令只传实际构建的包参数。

```powershell
$lanIp = '192.168.1.23'
$origin = "https://${lanIp}:8843"
python -B -m proposal_app.build_plugin_pilot --target windows --origin $origin --output deliverables/research-coach-windows-lan.zip
python -B -m proposal_app.build_plugin_pilot --target macos --origin $origin --output deliverables/research-coach-macos-lan.zip
python -B -m proposal_app.server --host 127.0.0.1 --port 8768 --db proposal_app/local_data/classroom.sqlite3 --no-demo --plugin-origin $origin --plugin-package deliverables/research-coach-windows-lan.zip --plugin-macos-package deliverables/research-coach-macos-lan.zip
```

## 2. 在同一台电脑开启 HTTPS

从 [Caddy 官方下载页](https://caddyserver.com/download)下载 Windows 版，将 `caddy.exe` 解压到一个文件夹。用记事本在同一文件夹新建 `Caddyfile`，保存时选择「所有文件」，把下面两个 IP 都改成自己的。

```caddyfile
{
    admin off
    auto_https disable_redirects
    skip_install_trust
}

https://192.168.1.23:8843 {
    bind 192.168.1.23
    tls internal
    reverse_proxy 127.0.0.1:8768
}
```

另开一个 PowerShell 窗口，进入这个文件夹后运行 `.\caddy.exe run --config .\Caddyfile`。保留 Python 和 Caddy 两个窗口。Caddy 负责让校园网里的浏览器通过 HTTPS 访问网站，并自动生成与 IP 匹配的证书。[Caddy 的本地 HTTPS 说明](https://caddyserver.com/docs/automatic-https)

如果第二台 Windows 电脑连不上，先在它上面运行 `Test-NetConnection 192.168.1.23 -Port 8843`。确认 Caddy 正在运行后，若端口仍不通，在部署电脑用管理员 PowerShell 放行本地子网到这个端口的连接。把命令中的 IP 换成自己的。[Windows 防火墙命令说明](https://learn.microsoft.com/powershell/module/netsecurity/new-netfirewallrule)

```powershell
New-NetFirewallRule -DisplayName '开题手记局域网试教' -Direction Inbound -Action Allow -Protocol TCP -LocalAddress 192.168.1.23 -LocalPort 8843 -RemoteAddress LocalSubnet
```

如果两台电脑在校园网内本身无法互访，换到允许设备互访的网络再试。

## 3. 让体验电脑信任试教站

在部署电脑复制 `%APPDATA%\Caddy\pki\authorities\local\root.crt` 给体验者。如果找不到，运行 `.\caddy.exe environ | Select-String '^caddy.AppDataDir='` 找到 Caddy 数据目录，再从里面取 `pki\authorities\local\root.crt`。只分发 `root.crt`，所有私钥留在部署电脑。

- **Windows**。体验者在保存 `root.crt` 的文件夹打开 PowerShell，运行 `Import-Certificate -FilePath .\root.crt -CertStoreLocation Cert:\CurrentUser\Root`。在弹出的确认框中核对证书来自本轮试教的部署者再确认。[微软导入证书说明](https://learn.microsoft.com/en-us/powershell/module/pki/import-certificate)
- **macOS**。用「钥匙串访问」导入 `root.crt`，打开该证书的「信任」，将 SSL 设为「始终信任」。如果浏览器能打开但插件报证书错误，需要再核对插件使用的 Python 是否信任同一个根证书。[苹果证书信任说明](https://support.apple.com/guide/keychain-access/kyca11871/mac)

在第二台电脑用 Chrome 或 Edge 打开 `https://192.168.1.23:8843`，确认浏览器没有证书提示。再登录试教账号，下载插件并完成三位码连接。网页能打开和插件能连接都确认后，再把地址发给全组。

如果部署电脑的 IP 变了，改 Caddyfile 和网站地址，按新地址重新打包插件。保留同一份 Caddy 数据目录，体验电脑可以继续使用已经导入的根证书。
