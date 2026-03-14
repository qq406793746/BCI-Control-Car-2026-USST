# online 目录说明

`code/online/` 是在线推理和仿真相关代码的主目录。

## 主入口

- `sender.py`
- `receiver.py`
- `receiver_i_trigger.py`
- `onlinev50pro.py`

## 子目录说明

- `onlinev50pro/`
  在线推理需要的模型产物
- `cue_timeline/`
  cue 时间线文本及相关生成脚本
- `analysis/`
  分析、验证、结果比对脚本
- `tools/`
  辅助工具脚本
- `scratch/`
  临时草稿脚本
- `media/`
  视频、截图、压缩备份
- `archive/`
  本地保留的重复副本或历史备份

## 整理原则

为了避免影响你已有运行方式，核心入口仍放在本目录根下，没有做进一步下沉。
