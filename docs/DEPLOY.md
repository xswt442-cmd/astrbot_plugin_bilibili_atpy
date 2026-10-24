# 部署

目标机器是 `tx-z01`（`43.142.116.197`），AstrBot 跑在 Docker Compose 里，插件目录挂在宿主机 `/opt/qq-ai/astrbot-data/plugins`。

插件目录**不是 Git 仓库**，服务器上也没有构建环境。所以部署是把 `git archive` 出来的发布包解压过去，不是 `git clone`。

## 一次部署

1. 确认本地在 `main` 上且干净：

   ```sh
   git switch main
   git status --short
   ```

2. 打发布包。`.gitattributes` 里的 `export-ignore` 会把 `icon/`、`test/`、`.github/`、`uv.lock` 排掉：

   ```sh
   git archive --format=tar --prefix=astrbot_plugin_bilibili_atpy/ -o atpy.tar HEAD
   tar -tf atpy.tar
   ```

3. 传上去并解压：

   ```sh
   scp atpy.tar tx-z01:~/atpy.tar
   ssh tx-z01 "sudo tar -xf ~/atpy.tar -C /opt/qq-ai/astrbot-data/plugins \
     && sudo chown -R root:root /opt/qq-ai/astrbot-data/plugins/astrbot_plugin_bilibili_atpy \
     && rm -f ~/atpy.tar"
   ```

4. 重启容器（会连带另外三个 bot 一起停几秒）：

   ```sh
   ssh tx-z01 "cd /opt/qq-ai && sudo docker compose restart astrbot"
   ```

5. 看加载结果：

   ```sh
   ssh tx-z01 "sudo docker logs --since 3m astrbot 2>&1 | grep -iE 'atpy'"
   ```

   正常时是这四行：

   ```
   Loading plugin astrbot_plugin_bilibili_atpy ...
   Plugin astrbot_plugin_bilibili_atpy (v0.1.9) by xswt442-cmd: ...
   [atpy] 后台调度已启动：每天 1-1 轮，9-23 点之间
   [atpy] 今天排了 N 轮：18:33、22:41
   ```

   排的轮数可能少于配置值：当前时间之前的分段会被跳过，不补跑。

## 覆盖升级

同上，`tar -x` 覆盖同名文件。`data/plugin_data/astrbot_plugin_bilibili_atpy/` 不在插件目录里，历史记录和排期不会被冲掉。

`plan.json` 只存当天。改活跃时段要等第二天生效；当天想立刻生效先删掉它再重启：

```sh
ssh tx-z01 "sudo rm /opt/qq-ai/astrbot-data/plugin_data/astrbot_plugin_bilibili_atpy/plan.json"
```

## 新装插件必须进白名单，否则指令一条都不响应

插件加载成功、handler 全部注册、`enabled=True`、`activated=True`、`command_configs` 里也没有禁用记录，但发 `/atpy 状态` 完全没反应，消息直接落进模型让它瞎编——先查这里。

每个 bot 的独立配置里有 `plugin_set` 白名单：`/opt/qq-ai/astrbot-data/config/abconf_<uuid>.json`。`waking_check` 用它过滤 handler，不在名单里的插件所有 `AdapterMessageEvent` handler 都会被跳过。`cmd_config.json` 里的 `["*"]` 会被 abconf 覆盖。

当前 `lg1(qq_official)` 对应 `abconf_94be3002-cfcd-40ba-8d4a-1b06d8a90e01.json`，映射关系在数据库 `preferences` 表的 `umop_config_routing`。

修法二选一：在 WebUI 配置页勾上插件（推荐），或直接改 json：

```sh
ssh tx-z01 "sudo python3 - <<'EOF'
import json
p='/opt/qq-ai/astrbot-data/config/abconf_94be3002-cfcd-40ba-8d4a-1b06d8a90e01.json'
d=json.load(open(p,encoding='utf-8-sig'))
d['plugin_set'].append('astrbot_plugin_bilibili_atpy')
json.dump(d,open(p,'w',encoding='utf-8-sig'),ensure_ascii=False,indent=2)
EOF"
```

改完重启容器才生效。文件带 BOM，读写都要 `utf-8-sig`。

以后换 bot、加 bot，各自的 abconf 都要单独加一次。
