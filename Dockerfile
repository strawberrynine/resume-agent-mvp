FROM python:3.12-slim

WORKDIR /app

# LibreOffice performs reliable legacy DOC conversion and preserves the
# backfilled DOCX layout when producing the final PDF. Noto provides CJK fonts
# in the Linux deployment image.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libreoffice-writer fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV GRADIO_SERVER_NAME=0.0.0.0
ENV PORT=7860
ENV SOFFICE_PATH=/usr/bin/soffice
ENV SAL_USE_VCLPLUGIN=svp
EXPOSE 7860

CMD ["python", "-m", "app.main"]
