import os
from supabase import create_client


SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")

if not SUPABASE_URL or not SUPABASE_ANON_KEY:
    raise RuntimeError("Variáveis SUPABASE_URL e SUPABASE_ANON_KEY não configuradas.")


def main():
    print("❤️ Heartbeat iniciado...")

    supabase = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

    # Query extremamente leve
    resp = supabase.table("clientes").select("id").limit(1).execute()

    if getattr(resp, "error", None):
        print("❌ Erro no heartbeat:", resp.error)
        raise SystemExit(1)

    total = len(resp.data) if resp.data else 0
    print(f"✅ Heartbeat OK. Registros lidos: {total}")


if __name__ == "__main__":
    main()
