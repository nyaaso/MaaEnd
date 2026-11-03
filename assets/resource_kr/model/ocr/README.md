# PaddleOCR Korean model

2026/11/03

from <https://huggingface.co/PaddlePaddle/korean_PP-OCRv5_mobile_rec> (Apache-2.0)

## rec model

korean_PP-OCRv5_mobile_rec  
PP-OCRv5 的韩文文本识别模型，支持韩文、英文与数字。  
使用 paddle2onnx 2.1.0（opset 14）从 `inference.json` / `inference.pdiparams` 转换为 ONNX。

## rec label

from `inference.yml` 的 `PostProcess.character_dict`（11945 字）。

## det model

不单独提供，沿用 `resource/model/ocr/det.onnx`（MaaFramework 会按资源加载顺序逐级回退查找）。
