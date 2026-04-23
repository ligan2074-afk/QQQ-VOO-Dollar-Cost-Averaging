# 纳指100自动定投打分系统

这是一个 **GitHub Pages + GitHub Actions** 的自动版示例：

- 网页端读取 `data/latest.json` 和 `data/history.json`
- 定时任务每天运行 `scripts/fetch_data.py`
- 自动拉取指数价格、波动率，计算 MA200、分项得分和综合得分
- 更新后的 JSON 自动提交回仓库
- 你每天打开页面就能看到最新结果

## 目录结构

```text
.
├── .github/workflows/update-data.yml
├── app.js
├── data
│   ├── config.json
│   ├── history.json
│   ├── latest.json
│   └── pe_history.json
├── index.html
├── requirements.txt
├── scripts/fetch_data.py
└── styles.css
```

## 默认评分逻辑

- **PE 得分（满分 30）**
  - 优先使用脚本预先算好的 `pePercentile`
  - 若没有预计算百分位，则回退到区间映射：
  - `pe_percentile = (pe - pe_min) / (pe_max - pe_min)`
  - `pe_score = (1 - pe_percentile) * 30`

- **MA200 得分（满分 40）**
  - `bias = (price - ma200) / ma200 * 100`
  - `ma_score = 40 * (1 - abs(bias - target_bias) / bias_range)`
  - 默认 `target_bias = -10`
  - 默认 `bias_range = 20`

- **VIX / VXN 得分（满分 30）**
  - `vix_score = ((vix - vix_floor) / (vix_cap - vix_floor)) * 30`
  - 默认 `vix_floor = 15`
  - 默认 `vix_cap = 30`

- **综合得分**
  - `total = pe_score + ma_score + vix_score`

## 自动抓数脚本说明

`scripts/fetch_data.py` 默认这样工作：

1. 从 FRED 拉取 `NASDAQ100` 日频收盘数据
2. 从 FRED 拉取 `VIXCLS` 日频收盘数据
3. 用价格序列自动计算 `MA200`
4. 从 `data/pe_history.json` 读取 PE 历史
5. 如果你配置了 `CURRENT_PE`，会自动把当天 PE 写入 `pe_history.json`
6. 如果你配置了 `PE_JSON_URL`，脚本会请求这个 JSON 地址，并把返回的 PE 写入 `pe_history.json`
7. 最终生成：
   - `data/history.json`
   - `data/latest.json`

### 支持的 PE 覆盖方式

#### 方式 A：最简单，手动填 Secret
在 GitHub 仓库的 Secrets 里加：

- `CURRENT_PE=31.25`

这样每次工作流运行时，会把这个数值写入最新交易日。

#### 方式 B：接你自己的 JSON 接口
在 Secrets 里加：

- `PE_JSON_URL=https://your-domain.com/pe.json`

这个接口返回下面两种格式之一即可：

```json
{"pe": 31.25}
```

或

```json
{"date": "2026-04-22", "pe": 31.25}
```

### 切换 VIX / VXN

默认是 `VIXCLS`。如果你更想用纳指专属波动率指数，可以把工作流里的：

```yaml
VOL_SERIES_ID: VIXCLS
```

改成：

```yaml
VOL_SERIES_ID: VXNCLS
```

## 本地运行

直接启动一个静态服务器：

```bash
python -m http.server 8000
```

浏览器打开：

```text
http://localhost:8000
```

如果你想本地执行抓数脚本：

```bash
pip install -r requirements.txt
export FRED_API_KEY=你的key
python scripts/fetch_data.py
```

Windows PowerShell 可以写成：

```powershell
pip install -r requirements.txt
$env:FRED_API_KEY="你的key"
python scripts/fetch_data.py
```

## 部署步骤

### 1. 创建 GitHub 仓库

把整个项目上传到一个 GitHub 仓库。

### 2. 配置 Pages

在仓库的 **Settings → Pages** 里：

- Source 选择 **Deploy from a branch**
- Branch 选择 `main`
- Folder 选择 `/ (root)`

### 3. 配置 Secrets

在 **Settings → Secrets and variables → Actions** 里至少加：

- `FRED_API_KEY`

可选：

- `CURRENT_PE`
- `PE_JSON_URL`

### 4. 等待自动更新

仓库里已经有 `.github/workflows/update-data.yml`，会按 cron 自动运行，也支持你在 Actions 页手动点 **Run workflow** 立即执行一次。

## 你后面最值得做的增强

- 接入一个真正稳定的 PE 数据源，让 PE 也完全自动化
- 增加标普 500 / 半导体指数 / 沪深 300 切换
- 增加“建议定投倍率”，例如 0.8x / 1.0x / 1.5x / 2.0x
- 增加 Telegram / 企业微信 / 邮件推送
- 把历史综合分做成折线图
