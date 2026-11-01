# 📦 Third-party components and licenses

> The complete license texts are kept alongside this index.

🌐 English · [简体中文](#简体中文)

MarkPrompt uses the following image and drag-and-drop components. This page serves as the third-party notice index.

| Component | Version | Purpose | License text |
| --- | --- | --- | --- |
| Pillow | 11.3.0 | Local image decoding | [MIT-CMU and bundled component notices](Pillow-LICENSE.txt) |
| tkinterdnd2 | 0.7.0 | Tkinter drag-and-drop integration | [MIT](tkinterdnd2-MIT.txt) |
| TkDND | 2.10.3 (current Windows x64 environment) | Native drag and drop | [Upstream license](tkdnd-license.terms) |

The tkinterdnd2 Python package and its bundled native TkDND library have separate version numbers. Native versions on other platforms depend on the installed package.

## 🔗 Sources

- [Pillow 11.3.0](https://pypi.org/project/pillow/11.3.0/) · [Upstream license](https://github.com/python-pillow/Pillow/blob/11.3.0/LICENSE)
- [tkinterdnd2 0.7.0](https://pypi.org/project/tkinterdnd2/0.7.0/) · [Project](https://github.com/Eliav2/tkinterdnd2)
- [TkDND license](https://github.com/petasis/tkdnd/blob/master/license.terms)

## 📤 Distribution notes

- The project source and original author-supplied sample artwork use the MIT License. Third-party components retain their own licenses.
- Keep the dependency manifest and these notices with source distributions. When distributing third-party code or binaries, include their applicable copyright and license texts.
- `Pillow-LICENSE.txt` preserves the installed package's complete notices, including bundled native components; retain the whole file rather than only the opening Pillow license.
- This directory covers image and drag-and-drop dependencies, not a complete executable inventory. Check the notices for Python, Tcl/Tk, the packaging runtime, and other components actually included in a build.

GitHub's dependency graph displays dependency and license information; it does not replace the supplied license texts. [GitHub documentation](https://docs.github.com/en/code-security/concepts/supply-chain-security/dependency-graph).

---

## 简体中文

MarkPrompt 使用以下图片处理和拖拽组件。此页作为第三方声明索引，完整许可文本保留在同一目录。

| 组件 | 版本 | 用途 | 许可原文 |
| --- | --- | --- | --- |
| Pillow | 11.3.0 | 本地图片解码 | [MIT-CMU 及安装包附带组件声明](Pillow-LICENSE.txt) |
| tkinterdnd2 | 0.7.0 | Tkinter 拖拽接入 | [MIT](tkinterdnd2-MIT.txt) |
| TkDND | 2.10.3（当前 Windows x64 环境） | 原生拖拽 | [上游许可](tkdnd-license.terms) |

Python 包 tkinterdnd2 与其附带的 TkDND 原生库分别使用自己的版本号。其他平台的原生库版本以实际安装包为准。

### 🔗 来源

- [Pillow 11.3.0](https://pypi.org/project/pillow/11.3.0/) · [上游许可](https://github.com/python-pillow/Pillow/blob/11.3.0/LICENSE)
- [tkinterdnd2 0.7.0](https://pypi.org/project/tkinterdnd2/0.7.0/) · [项目主页](https://github.com/Eliav2/tkinterdnd2)
- [TkDND 许可](https://github.com/petasis/tkdnd/blob/master/license.terms)

### 📤 发布说明

- 项目源码及作者提供的原创示例图片采用 MIT 许可证；第三方组件仍按各自许可分发。
- 发布源码时保留依赖清单和本目录中的声明。分发第三方代码或二进制组件时，附上相应版权与许可文本。
- `Pillow-LICENSE.txt` 保留所用安装包中的完整声明，包括其附带底层组件的许可；不能只保留文件开头的 Pillow 许可。
- 本目录覆盖图片与拖拽依赖，不代表可执行文件的完整组件清单。打包时需核对 Python、Tcl/Tk、打包运行时及其他实际附带组件的声明。

GitHub 的依赖图可展示依赖关系与许可信息，不能代替项目附带的许可原文。[GitHub 文档](https://docs.github.com/en/code-security/concepts/supply-chain-security/dependency-graph)。
