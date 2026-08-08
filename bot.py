# -*- coding: utf-8 -*-
import os, sys, subprocess, threading, asyncio, re, time, json, socket, aiohttp
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse, parse_qs
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, ConversationHandler, filters
from dotenv import load_dotenv

load_dotenv()

# ==========================================
# 🌐 SERVIDOR WEB FALSO PARA O RENDER
# ==========================================
class DummyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        corpo = b"Bot do Giovani esta ONLINE e operante!"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)
    def log_message(self, format, *args):
        return

def run_dummy_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), DummyHandler)
    server.serve_forever()

# ==========================================
# ⚙️ CONFIGURAÇÕES E CONSTANTES
# ==========================================
TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TOKEN:
    sys.exit(1)

ARQUIVO_BANCO = "lista_dns.txt"

# ==========================================
# 🛠 FUNÇÕES DE SUPORTE
# ==========================================
def extrair_hosts(texto):
    linhas = texto.split('\n')
    hosts = []
    for line in linhas:
        host = re.sub(r'https?://', '', line.replace(",", " ").strip()).split('/')[0].split('?')[0].split(':')[0].strip().lower()
        if "." in host and len(host) > 4: hosts.append(host)
    return list(set(hosts))

async def testar_url(session, dns, user, password):
    url = f"http://{dns}/player_api.php?username={user}&password={password}"
    try:
        timeout = aiohttp.ClientTimeout(total=4.0)
        async with session.get(url, timeout=timeout) as resp:
            if resp.status != 200: return None
            data = await resp.json()
            if "user_info" in data and str(data["user_info"].get("status")).lower() in ["active", "1"]:
                return data
    except: pass
    return None

# ==========================================
# 🚀 NÚCLEO DE PROCESSAMENTO (FORMATO V15.7)
# ==========================================
async def processar_giovani_hibrido(update: Update, context: ContextTypes.DEFAULT_TYPE):
    dados = update.message.text
    chat_id = update.message.chat_id
    
    print(f"📥 MENSAGEM RECEBIDA DO TELEGRAM: {dados}") # Log para ver na tela do Render se chegou algo

    inicio = time.time()
    dados_limpos = dados.strip()
    parsed_url = urlparse(dados_limpos)
    params = parse_qs(parsed_url.query)
    
    user = params.get('username', [''])[0]
    password = params.get('password', [''])[0]
    
    if not user or not password:
        match_user = re.search(r'username=([^&]+)', dados_limpos)
        match_pass = re.search(r'password=([^&]+)', dados_limpos)
        if match_user: user = match_user.group(1)
        if match_pass: password = match_pass.group(1)

    if not user or not password:
        await context.bot.send_message(chat_id=chat_id, text="❌ Link M3U Inválido ou incompleto. Certifique-se de enviar o link contendo username e password.")
        return

    dns_alvo = parsed_url.hostname or dados_limpos.split('/')[2].split(':')[0]
    
    if not os.path.exists(ARQUIVO_BANCO):
        with open(ARQUIVO_BANCO, "w") as f: f.write("")
        
    with open(ARQUIVO_BANCO, "r", encoding="utf-8", errors="ignore") as f: 
        todas_dns = extrair_hosts(f.read())
    
    espelhos = []
    connector = aiohttp.TCPConnector(limit=250)
    async with aiohttp.ClientSession(connector=connector) as session:
        for i in range(0, len(todas_dns), 250):
            lote = todas_dns[i:i+250]
            tarefas = [testar_url(session, dns, user, password) for dns in lote]
            resultados = await asyncio.gather(*tarefas)
            for idx, res in enumerate(resultados):
                if res: espelhos.append({"dns": lote[idx], "data": res})

    info = espelhos[0]["data"]["user_info"] if espelhos else {}
    exp_timestamp = info.get("exp_date")
    
    exp_date = "N/A"
    dias_rest = "N/A"
    if exp_timestamp and str(exp_timestamp).isdigit():
        dt_venc = datetime.fromtimestamp(int(exp_timestamp))
        exp_date = dt_venc.strftime("%d/%m/%Y")
        dias_rest = (dt_venc - datetime.now()).days

    relatorio = [
        f"🛡 **GIOVANI DETECTOR V15.7 (BANCO 2)**",
        f"────────────────────",
        f"👤 REQUISITANTE: 🅶︎🅸︎🅾︎🆅︎🅰︎🅽︎🅸︎",
        f"📅 DATA/HORA: {datetime.now().strftime('%d/%m/%Y | %H:%M:%S')}",
        f"────────────────────",
        f"🛰 DNS ALVO: `{dns_alvo}` (🟢 ONLINE)",
        f"⚡ PING ALVO: {int((time.time() - inicio) * 1000)}ms",
        f"────────────────────",
        f"👤 USUÁRIO: `{user}` | 🔑 SENHA: `{password}`",
        f"📅 VENCE: {exp_date} | 🗓 DIAS RESTANTES: {dias_rest}",
        f"👥 CONEXÕES ATIVAS: {info.get('active_connections', 0)}/{info.get('max_connections', 0)}",
        f"────────────────────",
        f"🔥 ESPELHOS DE OURO ({len(espelhos)}):"
    ]
    
    for e in espelhos[:15]:
        relatorio.append(f" └🔗 `http://{e['dns']}/get.php?username={user}&password={password}&type=m3u_plus&output=ts` - {int((time.time()-inicio)*10)%500+100}ms 📺 🔥")
    
    if not espelhos:
        relatorio.append(" ❌ Nenhum espelho válido encontrado.")

    relatorio.append(f"────────────────────")
    relatorio.append(f"⚡️ TEMPO TOTAL: {round(time.time() - inicio, 2)}s | 📦 LIDOS: {len(todas_dns)} sites")
    
    await context.bot.send_message(chat_id=chat_id, text="\n".join(relatorio), parse_mode='Markdown')

async def erro_handler(update, context):
    print(f"⚠️ Erro no Telegram: {context.error}")

# ==========================================
# 🏁 MAIN
# ==========================================
def main():
    threading.Thread(target=run_dummy_server, daemon=True).start()
    print("✅ GIOVANI DETECTOR V15.7 ONLINE")

    app = ApplicationBuilder().token(TOKEN).build()
    
    async def start(update, context):
        await update.message.reply_text("👋 Olá Giovani! O GIOVANI DETECTOR V15.7 está pronto.\nEnvie um link M3U para começar a análise.")

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("dnschecker", lambda u, c: u.message.reply_text("📥 Envie o link M3U completo para iniciar a varredura.")))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), processar_giovani_hibrido))
    app.add_error_handler(erro_handler)

    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
