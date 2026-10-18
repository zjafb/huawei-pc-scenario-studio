# v2 部署说明

新版以 README.md 为准，支持55个产品和四渠道，已取消逐条签字；旧D14私有白名单不再是新版运行前提。

## 本地

运行 `powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\start.ps1 -Port 7861`，打开 http://127.0.0.1:7861/ 。模型凭证在用户目录，不进入项目。默认本地资料模式。

## Docker

本机没有Docker，以下自建Docker命令未在本机执行。魔搭托管的Gradio构建已真实运行，具体入口见下方。

1. `docker build -t huawei-pc-agent .`
2. 私下准备 `.env`，设置模型令牌与模型ID；实时模式另配ima凭证。不提交该文件。
3. 私有挂载完整v7目录，设置 `APP_KB_DIR` 指向挂载目录；私有挂载 `data/private/asset-review-v2.json`，设置 `APP_ASSET_REVIEW` 指向该JSON。
4. 启动容器，映射7860端口。入口 `python run.py` 监听 `0.0.0.0:7860`。真实资料不应进入公开镜像。
5. 运行记录默认不持久化，需留存时另挂载私有可写目录到 `/app/data/private/runs`。不要挂载整个用户目录。

## 魔搭创空间

当前使用 Gradio 创空间，入口 app.py，免费 platform/2v-cpu-8g-mem，公开体验且源码不可见（protected）。SDK基础版本6.29.1，requirements安装项目实际使用的6.30.0。模型与ima凭证使用平台密文变量，原件仅进入源码不可见的私有部署检出目录，不进入GitHub。

- 体验入口：https://www.modelscope.cn/studios/zzklcd/huawei-pc-scenario-studio
- 公开源码：https://github.com/zjafb/huawei-pc-scenario-studio

初版已到达Running并确认云端可选55产品；后续修正版仍须以当前页面与真实运行验收为准，不用旧版状态冒充新部署。源码包保持不含知识库，团队在protected仓库中单独提供private-materials/kb与asset-review-v2.json，并仅在该检出目录的.dockerignore允许private-materials。

实际验收应包括：页面可访问、55产品目录可选、模型真实生成、原图展示、HTML下载、重启后私有配置仍可用、未登录浏览器可打开提交链接。没做的标未验证。实时模式必须另验证ima本次查库/原文/图片均成功，不能拿本地模式的结果冒充。

## 自动检查和真实验收

- `python tools/run_checks.py`：禁止真实连接器联网，不耗额度。
- `python tools/check_readiness.py`：检查目录、原件和配置存在性，不输出凭证，不联网。
- `python tools/check_full_flow.py --run`：真实模型四渠道验收，会耗模型额度；可加 `--channel xhs` 单测渠道。结果包含真实状态、篇幅、图数和运行编号。
- `python tools/package_release.py`：明确文件清单打包、凭证扫描、文件指纹清单；排除私有资料、元数据、运行记录、v7原件和协作日志。
- Git暂存后运行 `python tools/check_release.py`。此扫描不覆盖历史提交，也不自动取得资料传播许可。

源码包可独立运行自动检查。资料不在公开包中，涉及真实私有资料的检查会明确跳过，不能当作已核。完整运行依赖团队本机或私有挂载的资料。
