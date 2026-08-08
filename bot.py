# -*- coding: utf-8 -*-
import os, sys, subprocess, threading, asyncio, re, time, json, socket, aiohttp
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse, parse_qs
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, ConversationHandler, filters
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

# Bancos disponíveis (você pode adicionar mais arquivos de texto no Render se quiser)
BANCOS_DISPONIVEIS = {
    "banco_principal": "lista_dns.txt",
    "banco_secundario": "banco_extra.txt"
}

# Estados da Conversa
ESPERANDO_LINK = 1

# Armazenamento temporário por usuário
DADOS_USUARIO = {}

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
        timeout = aiohttp.ClientTimeout(total=3.5) # Timeout otimizado para mais velocidade
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
async def executar_varredura(chat_id, context, link_m3u, modo="completa", banco_escolhido="banco_principal"):
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
    
    # Seleciona o arquivo de banco
    arquivo_banco = BANCOS_DISPONIVEIS.get(banco_escolhido, "lista_dns.txt")
    if not os.path.exists(arquivo_banco):
        with open(arquivo_banco, "w") as f: f.write("")
        
    with open(arquivo_banco, "r", encoding="utf-8", errors="ignore") as f: 
        todas_dns = extrair_hosts(f.read())
    
    if modo == "rapida":
        todas_dns = todas_dns[:1500] # Varredura rápida nos primeiros 1.500

    total_sites = len(todas_dns)
    
    msg_status = await context.bot.send_message(
        chat_id=chat_id, 
        text=f"🚀 **Iniciando Turbo V15.8** ({modo.upper()})\n📦 Alvo: {total_sites} sites\n⏳ Progresso: 0%"
    )

    espelhos = []
    connector = aiohttp.TCPConnector(limit=500) # Turbo: 500 conexões simultâneas
    
    async with aiohttp.ClientSession(connector=connector) as session:
        tamanho_lote = 500 # Lotes maiores para voar na velocidade
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
        f"⚡ MODO: {modo.upper()} | BANCO: {banco_escolhido}",
        f"────────────────────",
        f"👤 USUÁRIO: `{user}` | 🔑 SENHA: `{password}`",
        f"📅 VENCE: {exp_date} | 🗓 DIAS RESTANTES: {dias_rest}",
        f"👥 CONEXÕES ATIVAS: {info.get('active_connections', 0)}/{info.get('max_connections', 0)}",
        f"────────────────────",
        f"🔥 ESPELHOS DE OURO ENCONTRADOS: {len(espelhos)}"
    ]
    
    # Mostra os 15 primeiros no chat
    for e in espelhos[:15]:
        relatorio.append(f" └🔗 `http://{e['dns']}/get.php?username={user}&password={password}&type=m3u_plus&output=ts` - 📺 🔥")
    
    if len(espelhos) > 15:
        relatorio.append(f" _...e mais {len(espelhos) - 15} espelhos no arquivo TXT abaixo._")

    if not espelhos:
        relatorio.append(" ❌ Nenhum espelho válido encontrado.")

    relatorio.append(f"────────────────────")
    relatorio.append(f"⚡️ TEMPO TOTAL: {tempo_total}s | 📦 LIDOS: {total_sites} sites")
    
    # Envia o relatório em texto no chat
    await context.bot.send_message(chat_id=chat_id, text="\n".join(relatorio), parse_mode='Markdown')

    # Gera e envia o arquivo .txt com TODOS os espelhos se houver resultados
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
# 🎛 FLUXO DO BOT (COM BOTÕES INTERATIVOS)
# ==========================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 **Olá Giovani! O GIOVANI DETECTOR V15.8 TURBO está online.**\n\n"
        "📥 Envie o link M3U completo da linha que deseja escanear:"
    )
    return ESPERANDO_LINK

async def receber_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text
    if not ("username=" in texto or "password=" in texto):
        await update.message.reply_text("❌ Isso não parece um link M3U válido. Envie um link contendo username e password:")
        return ESPERANDO_LINK

    # Salva o link temporariamente na memória do bot para o usuário
    DADOS_USUARIO[update.message.from_user.id] = texto

    # Cria o menu interativo com botões
    teclado = [
        [InlineKeyboardButton("🚀 Varredura Completa (11k+ sites)", callback_data="modo_completa")],
        [InlineKeyboardButton("⚡ Varredura Rápida (Top 1.500 sites)", callback_data="modo_rapida")],
        [InlineKeyboardButton("📂 Trocar Banco (Principal / Secundário)", callback_data="menu_bancos")]
    ]
    reply_markup = InlineKeyboardMarkup(teclado)

    await update.message.reply_text(
        "⚙️ **Link recebido com sucesso!**\nEscolha o modo de varredura desejado:",
        reply_markup=reply_markup
    )
    return ConversationHandler.END

async def botoes_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    chat_id = query.message.chat_id
    link = DADOS_USUARIO.get(user_id)

    if not link:
        await query.edit_message_text(text="❌ Sessão expirada. Envie o link M3U novamente enviando /start.")
        return

    dados_cb = query.data

    if dados_cb == "modo_completa":
        await query.edit_message_text(text="🚀 Iniciando Varredura Completa Turbo...")
        await executar_varredura(chat_id, context, link, modo="completa", banco_escolhido="banco_principal")
    elif dados_cb == "modo_rapida":
        await query.edit_message_text(text="⚡ Iniciando Varredura Rápida...")
        await executar_varredura(chat_id, context, link, modo="rapida", banco_escolhido="banco_principal")
    elif dados_cb == "menu_bancos":
        teclado_bancos = [
            [InlineKeyboardButton("📄 Banco Principal (lista_dns.txt)", callback_data="banco_principal")],
            [InlineKeyboardButton("📄 Banco Secundário (banco_extra.txt)", callback_data="banco_secundario")],
            [InlineKeyboardButton("🔙 Voltar", callback_data="modo_completa")]
        ]
        await query.edit_message_text(text="📂 Escolha qual base de dados quer utilizar:", reply_markup=InlineKeyboardMarkup(teclado_bancos))
    elif dados_cb in ["banco_principal", "banco_secundario"]:
        await query.edit_message_text(text=f"📂 Usando {dados_cb}. Iniciando varredura...")
        await executar_varredura(chat_id, context, link, modo="completa", banco_escolhido=dados_cb)

async def erro_handler(update, context):
    print(f"⚠️ Erro no Telegram: {context.error}")

# ==========================================
# 🏁 MAIN COM CONVERSATION HANDLER
# ==========================================
def main():
    threading.Thread(target=run_dummy_server, daemon=True).start()
    print("✅ GIOVANI DETECTOR V15.8 TURBO ONLINE")

    app = ApplicationBuilder().token(TOKEN).build()
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            ESPERANDO_LINK: [MessageHandler(filters.TEXT & (~filters.COMMAND), receber_link)]
        },
        fallbacks=[CommandHandler("start", start)]
    )

    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(botoes_callback))
    app.add_handler(CommandHandler("dnschecker", lambda u, c: u.message.reply_text("📥 Envie o link M3U para iniciar.")))
    app.add_error_handler(erro_handler)

    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
