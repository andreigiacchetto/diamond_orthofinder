# 🧬 diamond_orthofinder.py

An automated pipeline to run OrthoFinder using DIAMOND (or BLAST) with
efficient parallel execution and resume support for interrupted
analyses.

------------------------------------------------------------------------

## 🛠️ Features

-   Seamless integration with OrthoFinder (`-op` and `-b`)
-   Automatic generation of alignment commands (DIAMOND or BLAST)
-   True parallel execution (external multi-process jobs)
-   Checkpoint/resume system based on command hashing
-   Automatic conversion of `.diamond(.gz)` files to
    OrthoFinder-compatible format (`BlastX_Y.txt`)
-   Automatic detection of `WorkingDirectory`
-   Avoids recomputation of existing results
-   Progress logging (`blast_progress.log`)

------------------------------------------------------------------------

## 📦 Requirements

-   Python 3.x
-   OrthoFinder installed and available in PATH
-   DIAMOND (recommended) or BLAST+
-   Linux/Unix system

------------------------------------------------------------------------

## ▶️ Usage

``` bash
python diamond_orthofinder.py \
    -i /path/to/fasta_dir \
    -o /path/to/output \
    -t 32 \
    -s diamond
```

------------------------------------------------------------------------

## 🔄 Pipeline Overview

### PHASE 1 -- Preparation

    orthofinder -f INPUT -o OUTPUT -op

### PHASE 2 -- Parallel alignments

Runs multiple alignments simultaneously with 1 thread per job.

### PHASE 2.5 -- Conversion

Converts `.diamond(.gz)` → `BlastX_Y.txt`

### PHASE 3 -- Finalization

    orthofinder -og -b WorkingDirectory

------------------------------------------------------------------------

## ⚡ Parallelization

The script enforces: - DIAMOND: `-p 1` - BLAST: `-num_threads 1`

Parallelization is achieved by running multiple processes.

------------------------------------------------------------------------

## ♻️ Resume capability

File generated:

    blast_progress.log

Allows automatic continuation of interrupted runs.

------------------------------------------------------------------------

## 📁 Expected structure

### Input

    /input_dir/
    ├── genome1.faa
    ├── genome2.faa

### Output

    /output_dir/
    └── OrthoFinder/
        └── WorkingDirectory/

------------------------------------------------------------------------

## 🧪 Example

``` bash
python diamond_orthofinder.py -i ./proteins -o ./out -t 64 -s diamond
```

------------------------------------------------------------------------

## ❗ Notes

-   Automatically detects `WorkingDirectory`
-   Does not reprocess existing files
-   Compatible with `.diamond.gz`

------------------------------------------------------------------------

## 📄 License

Free for academic use.

------------------------------------------------------------------------

## ✨ Author

Andrei Giacchetto Felice
