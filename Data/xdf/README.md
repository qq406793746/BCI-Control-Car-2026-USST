# XDF 目录说明

这个目录放 `.xdf` 数据文件。

当前默认示例文件：

- `eeg_workflow_20260312_181155.xdf`

项目里以下脚本默认会读取这个目录下的文件：

- `code/online/tools/xdf_lsl_sender.py`
- `code/online/tools/run_xdf_simulation.py`
- `code/online/analysis/xdf_inference_test.py`

如果你后续更换 `.xdf` 文件，建议继续保持：

- 文件放在 `Data/xdf/`
- 文件名尽量使用小写、下划线分隔
