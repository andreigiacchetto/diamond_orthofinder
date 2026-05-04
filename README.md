# 🧬 diamond_orthofinder

Pipeline automatizado para executar o OrthoFinder utilizando DIAMOND (ou
BLAST) com execução paralela eficiente e suporte a retomada de análises
interrompidas.

------------------------------------------------------------------------

## 🛠️ Features

-   Integra automaticamente com o OrthoFinder (`-op` e `-b`)
-   Geração automática de comandos de alinhamento (DIAMOND ou BLAST)
-   Execução paralela real (multi-processo externo)
-   Sistema de checkpoint/retomada baseado em hash dos comandos
-   Conversão automática de arquivos `.diamond(.gz)` para formato
    compatível (`BlastX_Y.txt`)
-   Detecção automática do `WorkingDirectory`
-   Evita recomputação de resultados já existentes
-   Logging de progresso (`blast_progress.log`)

------------------------------------------------------------------------

## 📦 Requirements

-   Python 3.x
-   OrthoFinder instalado e no PATH
-   DIAMOND (recomendado) ou BLAST+
-   Sistema Linux/Unix

------------------------------------------------------------------------

## ▶️ Usage

``` bash
python diamond_orthofinder.py \
    -i /caminho/para/fasta_dir \
    -o /caminho/saida \
    -t 32 \
    -s diamond
```

------------------------------------------------------------------------

## 🔄 Pipeline Overview

### FASE 1 -- Preparação

Executa:

    orthofinder -f INPUT -o OUTPUT -op

### FASE 2 -- Alinhamentos paralelos

Executa múltiplos alinhamentos simultaneamente com 1 thread por job.

### FASE 2.5 -- Conversão

Converte `.diamond(.gz)` → `BlastX_Y.txt`

### FASE 3 -- Finalização

Executa:

    orthofinder -og -b WorkingDirectory

------------------------------------------------------------------------

## ⚡ Paralelização

O script força: - DIAMOND: `-p 1` - BLAST: `-num_threads 1`

E paraleliza via múltiplos processos.

------------------------------------------------------------------------

## ♻️ Retomada automática

Arquivo gerado:

    blast_progress.log

Permite continuar execuções interrompidas automaticamente.

------------------------------------------------------------------------

## 📁 Estrutura esperada

### Input

    /input_dir/
    ├── genome1.faa
    ├── genome2.faa

### Output

    /output_dir/
    └── OrthoFinder/
        └── WorkingDirectory/

------------------------------------------------------------------------

## 🧪 Exemplo

``` bash
python diamond_orthofinder.py -i ./proteins -o ./out -t 64 -s diamond
```

------------------------------------------------------------------------

## ❗ Notes

-   Detecta automaticamente `WorkingDirectory`
-   Não reprocessa arquivos existentes
-   Compatível com `.diamond.gz`

------------------------------------------------------------------------

## 📄 License

Uso acadêmico livre.

------------------------------------------------------------------------

## ✨ Author

Andrei Giacchetto Felice
