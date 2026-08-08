# -*- coding: utf-8 -*-
import os, sys, subprocess, threading, asyncio, re, time, json, socket, aiohttp
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse, parse_qs
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from dotenv import load_dotenv

load_dotenv()

# ==========================================
# 🌐 SERVIDOR WEB PARA O RENDER (MANTÉM VIVO)
# ==========================================
class DummyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"OK")
    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()
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
DADOS_USUARIO = {} # Armazena o link temporário do usuário

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
        timeout = aiohttp.ClientTimeout(total=3.5)
        async with session.get(url, timeout=timeout) as resp:
            if resp.status != 200: return None
            data = await resp.json()
            if "user_info" in data and str(data["user_info"].get("status")).lower() in ["active", "1"]:
                return data
    except: pass
    return None

# ==========================================
# 🚀 NÚCLEO DE PROCESSAMENTO TURBO V15.8
# ==========================================
async def executar_varredura(chat_id, context, link_m3u, modo="completa"):
    inicio = time.time()
    dados_limpos = link_m3u.strip()
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
        await context.bot.send_message(chat_id=chat_id, text="❌ Link M3U Inválido ou incompleto. Envie um link com username e password.")
        return

    dns_alvo = parsed_url.hostname or dados_limpos.split('/')[2].split(':')[0]
    
    if not os.path.exists(ARQUIVO_BANCO):
        with open(ARQUIVO_BANCO, "w") as f: f.write("")
        
    with open(ARQUIVO_BANCO, "r", encoding="utf-8", errors="ignore") as f: 
        todas_dns = extrair_hosts(f.read())
    
    if modo == "rapida":
        todas_dns = todas_dns[:1500]

    total_sites = len(todas_dns)
    
    msg_status = await context.bot.send_message(
        chat_id=chat_id, 
        text=f"🚀 **Iniciando Turbo V15.8** ({modo.upper()})\n📦 Alvo: {total_sites} sites\n⏳ Progresso: 0%"
    )

    espelhos = []
    connector = aiohttp.TCPConnector(limit=500)
    
    async with aiohttp.ClientSession(connector=connector) as session:
        tamanho_lote = 500
        total_lotes = (total_sites + tamanho_lote - 1) // tamanho_lote
        lote_atual = 0

        for i in range(0, total_sites, tamanho_lote):
            lote = todas_dns[i:i + tamanho_lote]
            lote_atual += 1
            
            tarefas = [testar_url(session, dns, user, password) for dns in lote]
            resultados = await asyncio.gather(*tarefas)
            
            for idx, res in enumerate(resultados):
                if res: 
                    espelhos.append({"dns": lote[idx], "data": res})

            porcentagem = int((lote_atual / total_lotes) * 100)
            sites_testados = min(i + tamanho_lote, total_sites)

            try:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=msg_status.message_id,
                    text=f"🚀 **Varredura Turbo em Andamento...**\n📊 Progresso: **{porcentagem}%** ({sites_testados}/{total_sites})\n🔥 Espelhos achados: {len(espelhos)}"
                )
            except Exception:
                pass

    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=msg_status.message_id)
    except Exception:
        pass

    info = espelhos[0]["data"]["user_info"] if espelhos else {}
    exp_timestamp = info.get("exp_date")
    
    exp_date = "N/A"
    dias_rest = "N/A"
    if exp_timestamp and str(exp_timestamp).isdigit():
        dt_venc = datetime.fromtimestamp(int(exp_timestamp))
        exp_date = dt_venc.strftime("%d/%m/%Y")
        dias_rest = (dt_venc - datetime.now()).days

    tempo_total = round(time.time() - inicio, 2)

    relatorio = [
        f"🛡 **GIOVANI DETECTOR V15.8 TURBO**",
        f"────────────────────",
        f"👤 REQUISITANTE: 🅶︎🅸︎🅾︎🆅︎🅰︎🅽︎🅸︎",
        f"📅 DATA/HORA: {datetime.now().strftime('%d/%m/%Y | %H:%M:%S')}",
        f"────────────────────",
        f"🛰 DNS ALVO: `{dns_alvo}` (🟢 ONLINE)",
        f"⚡ MODO: {modo.upper()}",
        f"────────────────────",
        f"👤 USUÁRIO: `{user}` | 🔑 SENHA: `{password}`",
        f"📅 VENCE: {exp_date} | 🗓 DIAS RESTANTES: {dias_rest}",
        f"👥 CONEXÕES ATIVAS: {info.get('active_connections', 0)}/{info.get('max_connections', 0)}",
        f"────────────────────",
        f"🔥 ESPELHOS DE OURO ENCONTRADOS: {len(espelhos)}"
    ]
    
    for e in espelhos[:15]:
        relatorio.append(f" └🔗 `http://{e['dns']}/get.php?username={user}&password={password}&type=m3u_plus&output=ts` - 📺 🔥")
    
    if len(espelhos) > 15:
        relatorio.append(f" _...e mais {len(espelhos) - 15} espelhos no arquivo TXT abaixo._")

    if not espelhos:
        relatorio.append(" ❌ Nenhum espelho válido encontrado.")

    relatorio.append(f"────────────────────")
    relatorio.append(f"⚡️ TEMPO TOTAL: {tempo_total}s | 📦 LIDOS: {total_sites} sites")
    
    await context.bot.send_message(chat_id=chat_id, text="\n".join(relatorio), parse_mode='Markdown')

    if espelhos:
        nome_arquivo = f"espelhos_{user}_{int(time.time())}.txt"
        conteudo_txt = f"# GIOVANI DETECTOR V15.8 - ESPELHOS DE OURO\n# Alvo: {dns_alvo} | Usuário: {user}\n\n"
        for e in espelhos:
            conteudo_txt += f"http://{e['dns']}/get.php?username={user}&password={password}&type=m3u_plus&output=ts\n"
        
        with open(nome_arquivo, "w", encoding="utf-8") as f:
            f.write(conteudo_txt)
            
        with open(nome_arquivo, "rb") as f:
            await context.bot.send_document(
                chat_id=chat_id,
                document=f,
                filename=nome_arquivo,
                caption=f"📁 **Lista Completa ({len(espelhos)} espelhos de ouro)**"
            )
        try:
            os.remove(nome_arquivo)
        except:
            pass

# ==========================================
# 🎛 HANDLERS DE MENSAGENS E BOTÕES
# ==========================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 **Olá Giovani! O GIOVANI DETECTOR V15.8 TURBO está online.**\n\n📥 Envie o link M3U completo da linha que deseja escanear:")

async def capturar_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text
    if not ("username=" in texto or "password=" in texto):
        return # Se não for um link, ignora

    user_id = update.message.from_user.id
    DADOS_USUARIO[user_id] = texto

    teclado = [
        [InlineKeyboardButton("🚀 Varredura Completa (11k+ sites)", callback_data="modo_completa")],
        [InlineKeyboardButton("⚡ Varredura Rápida (Top 1.500 sites)", callback_data="modo_rapida")]
    ]
    reply_markup = InlineKeyboardMarkup(teclado)

    await update.message.reply_text(
        "⚙️ **Link capturado com sucesso!**\nEscolha o modo de varredura:",
        reply_markup=reply_markup
    )

async def botoes_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    chat_id = query.message.chat_id
    link = DADOS_USUARIO.get(user_id)

    if not link:
        await query.edit_message_text(text="❌ Link não encontrado na memória. Envie o link M3U novamente.")
        return

    modo = "completa" if query.data == "modo_completa" else "rapida"
    
    await query.edit_message_text(text=f"🚀 Iniciando Varredura ({modo.upper()})... Aguarde.")
    await executar_varredura(chat_id, context, link, modo=modo)

async def erro_handler(update, context):
    print(f"⚠️ Erro no Telegram: {context.error}")

# ==========================================
# 🏁 MAIN
# ==========================================
def main():
    threading.Thread(target=run_dummy_server, daemon=True).start()
    print("✅ GIOVANI DETECTOR V15.8 TURBO ONLINE")

    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), capturar_link))
    app.add_handler(CallbackQueryHandler(botoes_callback))
    app.add_error_handler(erro_handler)

    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
