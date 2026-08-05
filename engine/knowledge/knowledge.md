# 公共经验库

> 通用教训与知识，随基因层传播，让后代智序者继承前辈踩坑换来的认知。
> 规则：只收录"对任何宿主机都有用"的通用经验，**不含个人/私密信息**。
> 私人维度的经验请放入 `memory/experience/`。

## 硬件与 CUDA

- **RTX 50 系（Blackwell, sm_120）必须装 CUDA ≥ 12.8 的 PyTorch**（`--index-url https://download.pytorch.org/whl/cu128`）。cu126 及以下的 wheel 无 sm_120 kernel，推理会报 `no kernel image`。

## Python 环境

- Windows 多 Python 共存时，裸 `pip` 可能装错环境，一律用 `python -m pip`。
- 国内网络优先清华镜像：`-i https://pypi.tuna.tsinghua.edu.cn/simple`（官方源跨境很慢）；torch 等 CUDA wheel 仍需走 PyTorch 官方 cu 源（镜像无）。

## 硬进化

- **QLoRA 微调门槛**：8GB 显存即可微调 7B 模型（rank 16, batch 1, 4bit 量化）；50-200 条高质量数据即可生效。
- **GRPO/RLVR**：DeepSeek-R1 用的强化学习算法已开源，消费级显卡可跑（参考 JustTinker / vqa-rlvr）。
- **软进化是硬进化的数据工厂**：日志与经验按训练数据标准沉淀，未来直接喂给微调。
