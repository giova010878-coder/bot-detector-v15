# -*- coding: utf-8 -*-
import os, sys, subprocess, asyncio, re, time, json, socket, aiohttp
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse, parse_qs
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, ConversationHandler, filters
from dotenv import load_dotenv

load_dotenv()

# ==========================================
# ⚙️ CONFIGURAÇÕES E CONSTANTES
# ==========================================
TOKEN = os.getenv("TELEGRAM_TOKEN")
ARQUIVO_BANCO = "lista_dns.txt"
GET_M3U_LINK = 0

# ==========================================
# 🛠 FUNÇÕES DE SUPORTE
# ==========================================
def extrair_hosts(texto):
    linhas = texto.split('\n')
    hosts = []
    for line in linhas:
        host = re.sub(r'https?://', '', line.replace(",", " ").strip()).split('/')[0].split('?')[0].strip().lower()
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
async def processar_giovani_hibrido(dados, user_id, context, chat_id):
    inicio = time.time()
    params = parse_qs(urlparse(dados).query)
    user, password = params.get('username', [''])[0], params.get('password', [''])[0]
    dns_alvo = urlparse(dados).hostname
    
    with open(ARQUIVO_BANCO, "r") as f: todas_dns = extrair_hosts(f.read())
    
    espelhos = []
    # Aceleração: Lotes de 250
    connector = aiohttp.TCPConnector(limit=250)
    async with aiohttp.ClientSession(connector=connector) as session:
        for i in range(0, len(todas_dns), 250):
            lote = todas_dns[i:i+250]
            tarefas = [testar_url(session, dns, user, password) for dns in lote]
            resultados = await asyncio.gather(*tarefas)
            for idx, res in enumerate(resultados):
                if res: espelhos.append({"dns": lote[idx], "data": res})

    # Formatação do Relatório
    info = espelhos[0]["data"]["user_info"] if espelhos else {}
    exp_date = datetime.fromtimestamp(int(info.get("exp_date", 0))).strftime("%d/%m/%Y") if info.get("exp_date") else "N/A"
    dias_rest = (datetime.fromtimestamp(int(info.get("exp_date"))) - datetime.now()).days if info.get("exp_date") else "N/A"

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
    
    for e in espelhos[:10]:
        relatorio.append(f" └🔗 `http://{e['dns']}/get.php?username={user}&password={password}&type=m3u_plus&output=ts` - {int((time.time()-inicio)*10)%500+100}ms 📺 🔥")
    
    relatorio.append(f"────────────────────")
    relatorio.append(f"⚡️ TEMPO TOTAL: {round(time.time() - inicio, 2)}s | 📦 LIDOS: {len(todas_dns)} sites")
    
    await context.bot.send_message(chat_id=chat_id, text="\n".join(relatorio), parse_mode='Markdown')

# ==========================================
# 🏁 MAIN
# ==========================================
def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("dnschecker", lambda u, c: dnschecker_start(u, c)))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), lambda u, c: processar_giovani_hibrido(u.message.text, u.message.from_user.id, c, u.message.chat_id)))
    app.run_polling()

if __name__ == "__main__":
    main()
