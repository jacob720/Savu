#!/bin/bash

echo "SAVU_MPI_LOCAL:: Running Job"

nNodes=1
nCoresPerNode=`grep '^core id' /proc/cpuinfo |sort -u|wc -l`
nGPUs=$(nvidia-smi -L | wc -l)

echo "***********************************************"
echo -e "\tRunning on $nCoresPerNode CPUs and $nGPUs GPUs"
echo "***********************************************"

datafile=$1
processfile=$2
outpath=$3
shift 3
options=$@

DIR="$(cd "$(dirname "$0")" && pwd)"

nCPUs=$((nNodes*nCoresPerNode))

# launch mpi job
export PYTHONPATH=$savupath:$PYTHONPATH

echo "running on host: "$HOSTNAME
echo "Processes running are : ${nCPUs}"

processes=`bc <<< "$nCPUs"`

for i in $(seq 0 $((nGPUs-1))); do GPUs+="GPU$i " ; done
for i in $(seq 0 $((nCPUs-1-nGPUs))); do CPUs+="CPU$i " ; done
CPUs=$(echo $GPUs$CPUs | tr ' ' ,)

echo "running the savu mpi local job"
mpirun -np $nCPUs -mca btl self,vader python -m savu.tomo_recon --memory-usage $filename $datafile $processfile $outpath -n $CPUs -v $options

echo "SAVU_MPI_LOCAL:: Process complete"

