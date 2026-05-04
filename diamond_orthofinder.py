#!/usr/bin/env python3
import os
import argparse
import subprocess
import sys
import re
import time
import hashlib
from pathlib import Path
import concurrent.futures
import threading

##############################################
# Globais
##############################################
# Lock para garantir que a escrita no log não encavale entre threads
log_lock = threading.Lock()

##############################################
# Funções auxiliares
##############################################

def _normalize_out_candidates(out_path):
    """
    OrthoFinder pode gerar:
        *.diamond
        *.diamond.gz
        BlastX_Y.txt
        BlastX_Y_Z.txt
    """
    candidates = [out_path]

    # versão .gz
    if not out_path.endswith(".gz"):
        candidates.append(out_path + ".gz")

    # se for .diamond, a versão .diamond.gz
    if out_path.endswith(".diamond"):
        candidates.append(out_path + ".gz")

    # fallback para padrão BlastX_Y(.Z).txt
    base = os.path.basename(out_path)
    m = re.match(r"(Species(\d+))_vs_(Species(\d+))\.(\d+)\.diamond", base)
    if m:
        qnum = m.group(2)
        tnum = m.group(4)
        frag = m.group(5)
        candidates.append(os.path.join(os.path.dirname(out_path), f"Blast{qnum}_{tnum}_{frag}.txt"))
        candidates.append(os.path.join(os.path.dirname(out_path), f"Blast{qnum}_{tnum}.txt"))
    else:
        # caso sem fragmento
        m2 = re.match(r"(Species(\d+))_vs_(Species(\d+))\.0\.diamond", base)
        if m2:
            qnum = m2.group(2)
            tnum = m2.group(4)
            candidates.append(os.path.join(os.path.dirname(out_path), f"Blast{qnum}_{tnum}.txt"))

    return candidates


def _command_hash(cmd_str):
    """Hash curto (12 chars) para identificar o comando no progress log."""
    return hashlib.sha1(cmd_str.encode("utf-8")).hexdigest()[:12]


##############################################
# Localiza WorkingDirectory
##############################################

def find_working_directory(output_dir):
    """
    Procura automaticamente um WorkingDirectory válido dentro do diretório de saída.
    """
    output_dir = Path(output_dir).resolve()
    if not output_dir.exists():
        return None

    for root, dirs, files in os.walk(output_dir):
        if os.path.basename(root) == "WorkingDirectory":
            return str(Path(root))
    return None


##############################################
# Carrega species e bancos DMND
##############################################

def load_species_and_dmnd(working_dir):
    """
    Retorna:
      species_map = { "Species0": ["Species0.fa"], ... }
      dmnd_map    = { "Species0": "diamondDBSpecies0.dmnd", ... }
    """
    wd = Path(working_dir)
    if not wd.exists():
        print("ERRO: WorkingDirectory inexistente.")
        return {}, {}

    species_map = {}
    dmnd_map = {}

    for f in os.listdir(wd):
        if re.match(r"Species\d+(\.\d+)?\.fa$", f):
            sp = f.split(".")[0]
            species_map.setdefault(sp, []).append(os.path.join(wd, f))

        if re.match(r"diamondDBSpecies\d+\.dmnd$", f):
            m = re.match(r"diamondDB(Species\d+)\.dmnd$", f)
            if m:
                sp = m.group(1)
                dmnd_map[sp] = os.path.join(wd, f)

    return species_map, dmnd_map


##############################################
# Geração dos comandos DIAMOND (padrão exato)
##############################################

def generate_blast_commands_txt(working_dir, species_map, dmnd_map, threads, search_engine="diamond"):
    """
    Gera os comandos.
    ALTERAÇÃO: Agora forçamos 1 thread por comando (-p 1 ou -num_threads 1),
    pois o paralelismo será feito executando vários comandos ao mesmo tempo.
    """
    commands = []
    out_commands_file = os.path.join(working_dir, "blast_commands.txt")

    query_species = sorted(species_map.keys())
    target_species = sorted(dmnd_map.keys())

    for q in query_species:
        q_fragments = species_map[q]

        for qf in q_fragments:
            base = os.path.basename(qf)
            # Identifica fragmento
            mm = re.match(r"Species\d+\.(\d+)\.fa$", base)
            if mm:
                frag = mm.group(1)
            else:
                frag = "0"

            for t in target_species:
                db = dmnd_map[t]

                out_file = f"{q}_vs_{t}.{frag}.diamond"
                out_path = os.path.join(working_dir, out_file)

                # AQUI: Fixamos threads=1 por comando individual
                if search_engine.lower() == "diamond":
                    cmd = (
                        f"diamond blastp --ignore-warnings -d {db} -q {qf} "
                        f"-o {out_path} --more-sensitive -p 1 "  # <-- FORÇADO 1 THREAD
                        f"--quiet -e 0.001 --compress 1"
                    )
                else:
                    cmd = (
                        f"blastp -db {db} -query {qf} "
                        f"-out {out_path} -num_threads 1 -evalue 0.001 -outfmt 6" # <-- FORÇADO 1 THREAD
                    )

                commands.append((cmd, out_path))

    with open(out_commands_file, "w") as fh:
        for cmd, _ in commands:
            fh.write(cmd + "\n")

    print(f"Gerado {len(commands)} comandos em: {out_commands_file}")
    return commands, out_commands_file


##############################################
# Worker individual (para rodar em paralelo)
##############################################

def _worker_blast(task):
    """
    Função executada por cada thread no Pool.
    Recebe: (cmd, out_path, working_dir, progress_file, done_hashes_set)
    """
    cmd, out_path, working_dir, progress_file, pre_done_hashes = task
    
    cmd_hash = _command_hash(cmd)

    # 1) Checagem rápida de Hash carregado no início
    # (Nota: não checamos o arquivo físico de log aqui para evitar I/O excessivo,
    #  confiamos no set carregado antes do pool)
    if cmd_hash in pre_done_hashes:
        return (False, f"Skipped (Hash): {os.path.basename(out_path)}")

    # 2) Checagem se arquivo de saída existe
    candidates = _normalize_out_candidates(out_path)
    for c in candidates:
        if os.path.exists(c) and os.path.getsize(c) > 0:
            # Se existe, precisamos registrar no log se não estiver lá, para futuras execuções?
            # Por segurança, vamos apenas marcar como feito e pular execução.
            with log_lock:
                with open(progress_file, "a") as pf:
                     pf.write(f"{time.time()}\t{cmd_hash}\t{out_path}\n")
            return (False, f"Skipped (Exists): {os.path.basename(c)}")

    # 3) Execução Real
    try:
        subprocess.run(cmd, shell=True, check=True, cwd=working_dir)
        
        # 4) Registrar sucesso (com Lock)
        with log_lock:
            with open(progress_file, "a") as pf:
                pf.write(f"{time.time()}\t{cmd_hash}\t{out_path}\n")
                
        return (True, f"Done: {os.path.basename(out_path)}")
        
    except subprocess.CalledProcessError as e:
        return (None, f"ERROR: {cmd} (Code {e.returncode})")


##############################################
# Execução com RETOMADA Paralela
##############################################

def run_blast_commands_parallel(commands, working_dir, num_threads, progress_file="blast_progress.log"):
    """
    Executa comandos em paralelo usando ThreadPoolExecutor.
    """
    total = len(commands)
    progress_file_path = os.path.join(working_dir, progress_file)

    # Carrega hashes existentes para memória antes de iniciar
    done_hashes = set()
    if os.path.exists(progress_file_path):
        for line in open(progress_file_path):
            parts = line.strip().split("\t")
            if len(parts) >= 2:
                done_hashes.add(parts[1])

    # Prepara as tarefas
    # task = (cmd, out_path, working_dir, progress_file_path, done_hashes)
    tasks = []
    for cmd, out_path in commands:
        tasks.append((cmd, out_path, working_dir, progress_file_path, done_hashes))

    print(f"\nIniciando execução paralela com {num_threads} workers...")
    
    # Executa
    completed_count = 0
    errors = 0
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        # map retorna na ordem, ou as_completed retorna assim que acaba.
        # as_completed é melhor para barra de progresso visual
        future_to_cmd = {executor.submit(_worker_blast, t): t for t in tasks}
        
        for future in concurrent.futures.as_completed(future_to_cmd):
            completed_count += 1
            status, msg = future.result()
            
            # Formatação simples de progresso
            if status is True:
                print(f"[{completed_count}/{total}] {msg}")
            elif status is False:
                # Opcional: imprimir skips pode poluir muito se forem milhares
                # Vamos imprimir apenas a cada 100 ou se for o último
                if completed_count % 100 == 0 or completed_count == total:
                    print(f"[{completed_count}/{total}] ... (skipping existing files) ...")
            else:
                print(f"[{completed_count}/{total}] {msg}")
                errors += 1

    if errors > 0:
        print(f"\nATENÇÃO: Houve {errors} erros durante a execução.")
        return False
        
    return True


def convert_diamond_to_blast_format(working_dir):
    """
    Converte arquivos SpeciesA_vs_SpeciesB.N.diamond(.gz)
    para BlastA_B[_N].txt no padrão exato que o OrthoFinder exige.
    """
    wd = Path(working_dir)
    # Lista tudo primeiro para não iterar sobre o que estamos criando
    files = list(os.listdir(wd))
    
    count = 0
    for f in files:
        m = re.match(r"Species(\d+)_vs_Species(\d+)\.(\d+)\.diamond(?:\.gz)?$", f)
        if not m:
            continue

        q = m.group(1)
        t = m.group(2)
        frag = m.group(3)

        # Nome de saída
        if frag == "0":
            out_name = f"Blast{q}_{t}.txt"
        else:
            out_name = f"Blast{q}_{t}_{frag}.txt"

        src_path = os.path.join(wd, f)
        dst_path = os.path.join(wd, out_name)

        # Se destino já existe, pula conversão
        if os.path.exists(dst_path) and os.path.getsize(dst_path) > 0:
            continue

        count += 1
        if count % 100 == 0:
            print(f"Convertendo arquivos... (processados: {count})")

        # DIAMOND --compress 1 gera .gz → precisamos descompactar antes
        if src_path.endswith(".gz"):
            import gzip
            with gzip.open(src_path, "rb") as f_in:
                with open(dst_path, "wb") as f_out:
                    f_out.write(f_in.read())
        else:
            # Apenas copiar
            with open(src_path, "rb") as f_in:
                with open(dst_path, "wb") as f_out:
                    f_out.write(f_in.read())
    
    print(f"Conversão concluída. Total convertidos nesta rodada: {count}")

##############################################
# MAIN
##############################################

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--input", required=True, help="Pasta com FASTAs (.faa)")
    parser.add_argument("-o", "--output", required=True, help="Diretório de saída")
    parser.add_argument("-t", "--threads", required=True, type=int, help="Número de jobs simultâneos")
    parser.add_argument("-s", "--search", default="diamond")
    args = parser.parse_args()

    input_dir = Path(args.input).resolve()
    output_dir = Path(args.output).resolve()

    # FASE 1: orthofinder -op
    print("\n=== FASE 1: Preparação ===")

    wd = find_working_directory(output_dir)
    if wd:
        print(f"WorkingDirectory encontrado: {wd} — pulando orthofinder -op.")
    else:
        # Aqui mantemos args.threads para o orthofinder preparar o DB rápido
        cmd = (
            f"orthofinder -f {input_dir} -o {output_dir} "
            f"-op -S {args.search} -t {args.threads} -a {args.threads}"
        )
        print(f"Comando FASE 1: {cmd}")
        subprocess.run(cmd, shell=True, check=True)

        wd = find_working_directory(output_dir)
        if not wd:
            print("ERRO: WorkingDirectory não encontrado após -op.")
            sys.exit(1)

    print(f"WorkingDirectory: {wd}")

    # Carrega species e bancos
    species_map, dmnd_map = load_species_and_dmnd(wd)

    # Gera comandos (AGORA FORÇANDO 1 THREAD INTERNA)
    commands, cmdfile = generate_blast_commands_txt(
        wd, species_map, dmnd_map, args.threads, args.search
    )

    # Executa comandos com retomada PARALELA
    print("\n=== FASE 2: Execução dos blasts em PARALELO ===")
    ok = run_blast_commands_parallel(commands, wd, num_threads=args.threads)
    if not ok:
        print("FASE 2 interrompida por erros.")
        sys.exit(1)

    print("\n=== FASE 2 concluída ===")

    print("\n=== FASE 2.5: Convertendo DIAMOND para formato Blast ===")
    convert_diamond_to_blast_format(wd)

    # FASE 3: orthofinder -b
    print("\n=== FASE 3: Finalizando ===")
    cmd = f"orthofinder -og -b {wd} -t {args.threads} -a {args.threads}"
    print(f"Comando final: {cmd}")
    subprocess.run(cmd, shell=True, check=True)

    print("\n=== Pipeline concluído com sucesso! ===")


if __name__ == "__main__":
    main()