现在zhihu爬虫中answer内容的图片已经可以正常下载并替换为[pic:filename]格式了。但是还有两个地方的图片处理需要完善：

1. **问题内容中的图片**：question字段中仍然显示为"[图片]"文本，需要下载实际图片并替换为[pic:filename]格式
2. **评论中的图片**：comments字段中仍然显示为"查看图片"文本，需要下载实际图片并替换为[pic:filename]格式

**具体要求：**
- 检查并实现question内容和comments内容中的图片提取和下载功能
- 将"[图片]"和"查看图片"等占位符替换为实际的图片文件名格式：[pic:image_xxx.webp]
- **重要**：确保同一个答案(answer)的所有图片（包括问题图片、答案图片、评论图片）都保存在同一个文件夹下，便于管理
- 保持与现有answer图片处理逻辑的一致性
- 确保图片去重逻辑也适用于问题和评论中的图片

请分析当前代码中question和comments的图片处理现状，并实现ok

ok
相应的图片下载和文本替换功能。

1、不要影响存量抓取功能。 @info.txt  是图片的元素信息
2、        "has_images": true,
        "images_processed": true,
        这两个参数是针对于答案中的图片的，请注意如果要应用到问题和评论中，需要修改对应的逻辑。
3、https://www.zhihu.com/question/1927090799402804312/answer/1927412011177861585
这里的问题中包含图片。

评论中的表情图片是没有必要抓取的 https://www.zhihu.com/question/1921501875582263828/answer/1924247390694650230 这个回答下面的评论第一条是由用户自己发的图片的，我需要的是这种。
<div class="CommentContent css-1jpzztt">现在的deepseek <img src="https://pic4.zhimg.com/v2-3bb879be3497db9051c1953cdf98def6.png" class="sticker" alt="[飙泪笑]"> <div class="comment_img css-1ztb8y"><img alt="" src="https://pic3.zhimg.com/v2-e2ae9d6de5ea2dca6d6f1f34b28adba2_xld.png" data-rawwidth="1717" data-rawheight="1296" data-original="https://pic3.zhimg.com/v2-e2ae9d6de5ea2dca6d6f1f34b28adba2.png" loading="lazy" class="css-8z95sv"></div></div>

如果需要，请使用mcp工具分析具体的元素信息

