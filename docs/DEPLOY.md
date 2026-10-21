# 部署

目标机器是 `tx-z01`（`43.142.116.197`），AstrBot 跑在 Docker Compose 里，
插件目录挂在宿主机 `/opt/qq-ai/astrbot-data/plugins`。

插件目录**不是 Git 仓库**，服务器上也没有构建环境。所以部署是把
`git archive` 出来的发布包解压过去，不是 `git clone`。

## 一次部署

1. 确认本地在 `main` 上且干净：

   ```sh
   git switch main
   git status --short
   ```

2. 打发布包。`.gitattributes` 里的 `export-ignore` 会把 `test/`、`.github/`、
   `uv.lock` 排掉，包里只剩运行时要用的东西：

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
   ssh tx-z01 "sudo docker logs --since 3m astrbot 2>&1 | grep -iE 'atpy|爱评'"
   ```

   正常时有这四行：

   ```
   Loading plugin astrbot_plugin_bilibili_atpy ...
   Plugin astrbot_plugin_bilibili_atpy (v0.1.0) by xswt442-cmd: ...
   [爱评] 后台调度已启动：每天 3-5 轮，9-23 点之间
   [爱评] 今天排了 N 轮：18:33、22:41
   ```

   排的轮数可能少于配置值：当前时间之前的分段会被跳过，不补跑。

## 覆盖升级

同上，`tar -x` 会覆盖同名文件。`data/plugin_data/astrbot_plugin_bilibili_atpy/`
不在插件目录里，历史记录和排期不会被冲掉。

## 排期是当天的

`plan.json` 只存当天。改活跃时段要等第二天生效；当天想立刻生效就先删掉：

```sh
ssh tx-z01 "sudo rm /opt/qq-ai/astrbot-data/plugin_data/astrbot_plugin_bilibili_atpy/plan.json"
```

然后重启容器，会按新配置重排。
