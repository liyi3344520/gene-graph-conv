#!/usr/bin/env bash
export HOME=`getent passwd $USER | cut -d':' -f6`
source ~/venv/bin/activate
for i in "$@"
do
case $i in
    -d=*|--baseline-dataset=*)
    dataset="${i#*=}"
    ;;
    -m=*|--baseline-model=*)
    model="${i#*=}"
    ;;
    -p=*|--param-value=*)
    param="${i#*=}"
    ;;
esac
done
python -W ignore ../../../baseline.py --log=silent --cuda --baseline-model=$model --baseline-dataset=$dataset