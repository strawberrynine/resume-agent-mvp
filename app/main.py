"""Entry point for the single-page ResumeFlow AI Gradio app."""

import os
import re
from collections.abc import Generator

import gradio as gr

from agent.resume_agent import ResumeAgent


CSS = """
:root {
  --cream: #fbfaf7;
  --surface: #ffffff;
  --tea: #c59b7d;
  --tea-soft: #f3e7dd;
  --brown: #4b302b;
  --ink: #2f2a28;
  --muted: #827771;
  --line: #e9e1dc;
  --pink: #e6a1aa;
  --pink-soft: #f9e8e9;
  --sage: #6d887d;
}

body, .gradio-container {
  background: var(--cream) !important;
  color: var(--ink) !important;
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif !important;
}

.gradio-container {
  max-width: 1440px !important;
  padding: 0 !important;
}

#page {
  min-height: 100vh;
  padding: 18px clamp(20px, 5vw, 72px) 42px;
}

#topbar {
  max-width: 1240px;
  margin: 0 auto 36px;
  align-items: center;
}

#brand {
  display: inline-flex;
  align-items: center;
  gap: 11px;
  color: var(--brown);
  font-weight: 760;
  letter-spacing: .01em;
  font-size: 16px;
}

.brand-mark {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border-radius: 12px;
  background: var(--brown);
  color: #f7e5d5;
  font-size: 18px;
  box-shadow: 0 5px 14px rgba(75, 48, 43, .18);
}

.nav-note {
  color: var(--muted);
  font-size: 12px;
  letter-spacing: .08em;
  text-transform: uppercase;
}

#hero {
  max-width: 1240px;
  margin: 0 auto 30px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 32px;
  align-items: end;
}

.eyebrow {
  color: var(--tea);
  font-size: 12px;
  font-weight: 750;
  letter-spacing: .14em;
  text-transform: uppercase;
  margin-bottom: 12px;
}

#hero h1 {
  color: var(--brown);
  font-size: clamp(36px, 5vw, 62px);
  line-height: 1.02;
  letter-spacing: -.035em;
  margin: 0 0 14px;
  max-width: 700px;
}

.hero-copy {
  color: var(--muted);
  font-size: 16px;
  line-height: 1.65;
  max-width: 580px;
  margin: 0;
}

.hero-badge {
  border: 1px solid var(--line);
  background: var(--surface);
  border-radius: 18px;
  padding: 14px 16px;
  min-width: 190px;
  color: var(--brown);
  font-size: 13px;
  line-height: 1.45;
  box-shadow: 0 10px 28px rgba(75, 48, 43, .06);
}

.hero-badge strong {
  display: block;
  font-size: 18px;
  margin-bottom: 2px;
}

#workspace {
  max-width: 1240px;
  margin: 0 auto;
  display: grid;
  grid-template-columns: minmax(300px, .86fr) minmax(0, 1.45fr);
  gap: 22px;
  align-items: start;
}

.panel, .result-card {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 20px;
  box-shadow: 0 16px 42px rgba(75, 48, 43, .07);
}

.panel {
  padding: 24px;
}

.panel-title {
  color: var(--brown);
  font-size: 17px;
  font-weight: 760;
  margin: 0 0 4px;
}

.panel-subtitle {
  color: var(--muted);
  font-size: 13px;
  margin: 0 0 20px;
}

#resume-upload {
  border: 1.5px dashed #d8c4b6;
  border-radius: 16px;
  background: #fffdfa;
  min-height: 162px;
  transition: border-color .2s ease, background .2s ease;
}

#resume-upload:hover {
  border-color: var(--tea);
  background: #fff8f1;
}

#resume-upload .file-preview, #resume-upload .upload-container {
  border: 0 !important;
  background: transparent !important;
}

#resume-upload label span {
  color: var(--brown) !important;
  font-weight: 680 !important;
}

#job-description textarea {
  border-radius: 14px !important;
  border: 1px solid var(--line) !important;
  background: #fffdfa !important;
  color: var(--ink) !important;
  min-height: 180px !important;
  line-height: 1.55 !important;
}

/* Gradio 6 may attach elem_id to either the component wrapper or its control. */
#job-description,
#job-description > div,
#job-description .wrap,
#job-description .container {
  background: transparent !important;
  border: 0 !important;
  box-shadow: none !important;
}

#job-description label,
#job-description label span {
  color: var(--brown) !important;
}

#job-description textarea,
textarea#job-description {
  border-radius: 14px !important;
  border: 1px solid var(--line) !important;
  background: #fffdfa !important;
  color: var(--ink) !important;
}

#job-description textarea:focus {
  border-color: var(--tea) !important;
  box-shadow: 0 0 0 3px rgba(197, 155, 125, .14) !important;
}

#analyze-button {
  margin-top: 18px;
}

#analyze-button button {
  width: 100%;
  min-height: 48px;
  border: 0 !important;
  border-radius: 14px !important;
  background: var(--brown) !important;
  color: #fffaf6 !important;
  font-size: 14px !important;
  font-weight: 740 !important;
  box-shadow: 0 10px 18px rgba(75, 48, 43, .18);
}

#analyze-button,
#analyze-button > button,
button#analyze-button {
  border: 0 !important;
  border-radius: 14px !important;
  background: var(--brown) !important;
  color: #fffaf6 !important;
  box-shadow: 0 10px 18px rgba(75, 48, 43, .18) !important;
}

#analyze-button > button:hover,
button#analyze-button:hover {
  background: #604039 !important;
}

#analyze-button button:hover {
  background: #604039 !important;
}

#status {
  min-height: 27px;
  margin-top: 10px;
}

#status p {
  color: var(--muted);
  font-size: 12px;
  text-align: center;
  margin: 0;
}

#dashboard-heading {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin: 0 0 12px;
}

#dashboard-heading h2 {
  color: var(--brown);
  font-size: 21px;
  margin: 0;
}

#dashboard-heading span {
  color: var(--muted);
  font-size: 12px;
}

#results-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 14px;
}

.result-card {
  padding: 20px;
  min-height: 174px;
  overflow: hidden;
}

.result-card-wide {
  grid-column: 1 / -1;
  min-height: 210px;
}

.result-card h3, .result-card h4 {
  color: var(--brown);
  margin: 0 0 10px;
  font-size: 15px;
  letter-spacing: .01em;
}

.result-card h3::before {
  content: "";
  display: inline-block;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  margin: 0 9px 2px 0;
  background: var(--pink);
}

.result-card p, .result-card li {
  color: var(--muted);
  font-size: 13px;
  line-height: 1.6;
}

.result-card ul {
  margin: 0;
  padding-left: 18px;
}

#score-card {
  background: #fffaf3;
}

#score-card h3::before {
  background: var(--tea);
}

#score-card h1 {
  color: var(--brown);
  font-size: 48px;
  line-height: 1;
  letter-spacing: -.04em;
  margin: 8px 0 4px;
}

#score-card .score-caption {
  color: var(--muted);
  font-size: 12px;
}

#history-card {
  background: #fdfcfa;
}

#history-card table {
  width: 100%;
  border-collapse: collapse;
  font-size: 11px;
}

#history-card th {
  color: var(--muted);
  font-weight: 650;
  text-align: left;
  padding: 4px 3px 8px;
  border-bottom: 1px solid var(--line);
}

#history-card td {
  color: var(--ink);
  padding: 7px 3px;
  border-bottom: 1px solid #f0ebe7;
}

#history-card td:nth-child(3) {
  color: var(--sage);
  font-weight: 700;
}

#interview-card {
  background: var(--pink-soft);
  border-color: #f0d4d5;
}

#knowledge-card {
  background: #f5f7f3;
  border-color: #dfe8e1;
}

#optimized-card {
  min-height: 260px;
}

#optimized-card pre, #optimized-card code {
  white-space: pre-wrap;
  word-break: break-word;
}

#footer {
  max-width: 1240px;
  margin: 24px auto 0;
  color: #a1948d;
  font-size: 11px;
  text-align: center;
}

@media (max-width: 900px) {
  #hero, #workspace {
    grid-template-columns: 1fr;
  }

  .hero-badge {
    width: fit-content;
  }
}

@media (max-width: 640px) {
  #page {
    padding: 16px 14px 30px;
  }

  #topbar {
    margin-bottom: 28px;
  }

  #hero h1 {
    font-size: 40px;
  }

  #results-grid {
    grid-template-columns: 1fr;
  }

  .result-card-wide {
    grid-column: auto;
  }

  .panel {
    padding: 18px;
  }
}
"""


def _empty_outputs() -> tuple[str, str, str, str, str, str, str]:
    """Return the initial state for all dashboard cards."""
    return (
        "### 简历匹配分数\n\n<span class='score-caption'>等待上传简历</span>",
        "### 评分历史\n\n评分变化会显示在这里。",
        "### 技能差距分析\n\n上传简历并粘贴目标职位描述后开始。",
        "### 简历优化\n\n个性化建议会显示在这里。",
        "### 面试问题\n\n分析完成后会生成准备提示。",
        "### 使用的知识库\n\n命中的本地简历指南会显示在这里。",
        "",
    )


def _split_sections(markdown: str) -> dict[str, str]:
    """Split agent Markdown output into named dashboard sections."""
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in markdown.splitlines():
        heading = re.match(r"^#\s+(.+?)\s*$", line)
        if heading:
            current = heading.group(1)
            sections[current] = []
        elif current is not None:
            sections[current].append(line)
    return {name: "\n".join(lines).strip() for name, lines in sections.items()}


def _score_card(score_markdown: str) -> str:
    """Render the score section with a large numeric visual."""
    lines = [line.strip() for line in score_markdown.splitlines() if line.strip()]
    score = next((line for line in lines if re.fullmatch(r"\d{1,3}", line)), "--")
    rationale = next((line for line in lines if line != score), "")
    return (
        "### 简历匹配分数\n\n"
        f"<h1>{score}<small>/100</small></h1>\n"
        f"<span class='score-caption'>{rationale or '从这里开始，让简历更贴近目标职位。'}</span>"
    )


def _interview_card(sections: dict[str, str]) -> str:
    """Render interview prompts, with a useful preview until that node is added."""
    content = sections.get("Interview Questions", "").strip()
    if content:
        return f"### 面试问题\n\n{content}"
    return (
        "### 面试问题\n\n"
        "*准备提示*\n\n"
        "- 请介绍一个与你申请职位最相关的项目。\n"
        "- 你如何评估工作的质量和实际影响？\n"
        "- 你接下来准备重点补齐哪项技能？"
    )


def _translate_history(markdown: str) -> str:
    """Translate stable score-history labels while preserving model content."""
    replacements = {
        "Iteration": "轮次",
        "Score": "评分",
        "Change": "变化",
        "Action": "动作",
        "Initial resume score": "初始简历评分",
        "Optimized resume and re-scored": "优化后重新评分",
    }
    for source, target in replacements.items():
        markdown = markdown.replace(source, target)
    return markdown


def _format_result(markdown: str) -> tuple[str, str, str, str, str, str, str]:
    """Map the agent's stable Markdown contract to the dashboard cards."""
    if not markdown.startswith("# "):
        error_message = markdown
        if error_message.startswith("Please upload"):
            error_message = "请先上传 PDF 简历。"
        elif error_message.startswith("Please paste"):
            error_message = "请先粘贴目标职位描述。"
        elif error_message.startswith("Analysis failed:"):
            error_message = error_message.replace("Analysis failed:", "分析失败：", 1)
        if "OPENAI_API_KEY is not configured" in error_message:
            error_message = "分析失败：尚未配置 OPENAI_API_KEY。请复制 .env.example 为 .env 并填写 API Key。"
        return (error_message, *_empty_outputs()[:6])

    sections = _split_sections(markdown)
    return (
        "<span class='status-ready'>分析完成，可以开始查看</span>",
        _score_card(sections.get("Resume Score", "")),
        f"### 评分历史\n\n{_translate_history(sections.get('Score History', '暂无评分记录。'))}",
        f"### 技能差距分析\n\n{sections.get('Missing Skills', '暂无明显技能差距。')}",
        f"### 简历优化\n\n{sections.get('Suggestions', '暂无优化建议。')}\n\n"
        f"#### 优化后的简历\n\n{sections.get('Optimized Resume', '暂无优化后的简历。')}",
        _interview_card(sections),
        f"### 使用的知识库\n\n{sections.get('Knowledge Used', '暂无命中的知识来源。')}",
    )


def build_demo() -> gr.Blocks:
    """Build the ResumeFlow AI single-page interface and wire analysis."""
    agent = ResumeAgent()

    def analyze_resume(
        pdf_path: str | None,
        job_description: str,
    ) -> Generator[tuple[str, str, str, str, str, str, str], None, None]:
        """Run the agent while exposing a lightweight companion status state."""
        yield (
            "<span class='status-working'>🐱 正在分析你的简历…</span>",
            *_empty_outputs()[:6],
        )
        yield (
            "<span class='status-working'>🐱 正在优化关键词…</span>",
            *_empty_outputs()[:6],
        )
        result = agent.analyze(pdf_path=pdf_path, job_description=job_description)
        yield _format_result(result)

    initial = _empty_outputs()
    with gr.Blocks(title="ResumeFlow AI") as demo:
        with gr.Column(elem_id="page"):
            with gr.Row(elem_id="topbar"):
                gr.HTML(
                    "<div id='brand'><span class='brand-mark'>🐱</span>"
                    "<span>ResumeFlow <strong>AI</strong></span></div>"
                )
                gr.HTML("<span class='nav-note'>更温暖的简历智能助手</span>")

            gr.HTML(
                "<section id='hero'><div><div class='eyebrow'>AI 简历智能助手</div>"
                "<h1>让你的经历，<br>被合适的职位看见。</h1>"
                "<p class='hero-copy'>为你的简历、目标职位，以及两者之间的故事，提供一双温柔而清晰的 AI 眼睛。</p>"
                "</div><div class='hero-badge'><strong>🐾 温柔但专业</strong>"
                "忠于真实经历，提炼关键信号。<br>陪你准备下一步。</div></section>"
            )

            with gr.Row(elem_id="workspace"):
                with gr.Column(elem_id="input-panel", elem_classes=["panel"]):
                    gr.HTML(
                        "<h2 class='panel-title'>从你的材料开始</h2>"
                        "<p class='panel-subtitle'>一份简历，一个目标职位，更清晰的下一步。</p>"
                    )
                    resume_file = gr.File(
                        label="PDF 简历",
                        file_types=[".pdf"],
                        type="filepath",
                        elem_id="resume-upload",
                    )
                    gr.HTML(
                        "<p class='upload-helper'>🐾 拖入 PDF，或点击选择文件</p>"
                    )
                    job_description = gr.Textbox(
                        label="目标职位描述",
                        lines=9,
                        placeholder="粘贴你想申请的职位描述…",
                        elem_id="job-description",
                    )
                    analyze_button = gr.Button(
                        "🐾  开始分析",
                        variant="primary",
                        elem_id="analyze-button",
                    )
                    status = gr.Markdown(initial[-1], elem_id="status")

                with gr.Column(elem_id="results-panel"):
                    gr.HTML(
                        "<div id='dashboard-heading'><h2>你的简历工作台</h2>"
                        "<span>私密工作区 · 不保存历史记录</span></div>"
                    )
                    with gr.Column(elem_id="results-grid"):
                        score_output = gr.Markdown(initial[0], elem_id="score-card", elem_classes=["result-card"])
                        history_output = gr.Markdown(initial[1], elem_id="history-card", elem_classes=["result-card"])
                        skill_output = gr.Markdown(initial[2], elem_id="skill-card", elem_classes=["result-card"])
                        optimization_output = gr.Markdown(
                            initial[3], elem_id="optimized-card", elem_classes=["result-card", "result-card-wide"]
                        )
                        interview_output = gr.Markdown(
                            initial[4], elem_id="interview-card", elem_classes=["result-card"]
                        )
                        knowledge_output = gr.Markdown(
                            initial[5], elem_id="knowledge-card", elem_classes=["result-card"]
                        )

            gr.HTML("<div id='footer'>ResumeFlow AI · 为每一次认真选择准备</div>")

        analyze_button.click(
            fn=analyze_resume,
            inputs=[resume_file, job_description],
            outputs=[
                status,
                score_output,
                history_output,
                skill_output,
                optimization_output,
                interview_output,
                knowledge_output,
            ],
            show_progress="hidden",
        )

    return demo


if __name__ == "__main__":
    build_demo().launch(
        server_name=os.getenv("GRADIO_SERVER_NAME", "127.0.0.1"),
        server_port=int(os.getenv("PORT", "7860")),
        css=CSS,
        theme=gr.themes.Base(),
    )
