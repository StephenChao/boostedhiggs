#!/usr/bin/python

from utils import axis_dict, add_samples, color_by_sample, signal_by_ch, data_by_ch, data_by_ch_2018, label_by_ch
from utils import get_simplified_label, get_sum_sumgenweight
import pickle as pkl
import pyarrow.parquet as pq
import pyarrow as pa
import awkward as ak
import numpy as np
import pandas as pd
import json
import os
import sys
import glob
import shutil
import pathlib
from typing import List, Optional

import argparse
from coffea import processor
from coffea.nanoevents.methods import candidate, vector
from coffea.analysis_tools import Weights, PackedSelection

import hist as hist2
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import mplhep as hep
from hist.intervals import clopper_pearson_interval

import warnings
warnings.filterwarnings("ignore", message="Found duplicate branch ")


def make_big_dataframe(year, channels, idir, odir, samples, tag=''):
    """
    Counts signal and background at different working points of a cut

    Args:
        year: string that represents the year the processed samples are from
        channels: list of channels... choices are ['ele', 'mu', 'had']
        idir: directory that holds the processed samples (e.g. {idir}/{sample}/outfiles/*_{ch}.parquet)
        odir: output directory to hold the hist object
        samples: the set of samples to run over (by default: the samples with key==1 defined in plot_configs/samples_pfnano.json)
    """
    max_iso = {'ele': 120, 'mu': 55}

    for ch in channels:
        c = 0
        # loop over the samples
        for sample in samples[year][ch]:
            if sample != 'VBFHToWWToLNuQQ-MH125':
                continue

            # skip data samples
            is_data = False
            for key in data_by_ch.values():
                if key in sample:
                    is_data = True
            if is_data:
                continue

            # check if the sample was processed
            pkl_dir = f'{idir}/{sample}/outfiles/*.pkl'
            pkl_files = glob.glob(pkl_dir)  #
            if not pkl_files:  # skip samples which were not processed
                continue

            # check if the sample was processed
            parquet_files = glob.glob(f'{idir}/{sample}/outfiles/*_{ch}.parquet')

            for i, parquet_file in enumerate(parquet_files):
                try:
                    data = pq.read_table(parquet_file).to_pandas()
                except:
                    continue

                try:
                    event_weight = data['tot_weight']
                except:
                    continue

                single_sample = None
                for single_key, key in add_samples.items():
                    if key in sample:
                        single_sample = single_key
                if single_sample is not None:
                    sample_to_use = single_sample
                else:
                    sample_to_use = sample

                # add iso and miso selection cuts
                if ch == 'ele':
                    select = (data['lep_isolation'] < 0.15) & (data['lep_pt'] < max_iso[ch]) | (data['lep_pt'] > max_iso[ch])
                elif ch == 'mu':
                    select = ((data['lep_isolation'] < 0.15) & (data['lep_pt'] < max_iso[ch])) | ((data['lep_misolation'] < 0.1) & (data['lep_pt'] > max_iso[ch]))

                # specefy variable to save
                if 'gen_Hpt' not in data.keys():
                    continue

                print(sample_to_use)

                if sample_to_use == 'VBFHToWWToLNuQQ-MH125':
                    print(data['gen_Hpt'][select])

                if c == 0:  # just so that the first iteration the dataframe is initialized (then for further iterations we can just concat)
                    data_all = pd.DataFrame(data['gen_Hpt'][select])
                    data_all['sample'] = sample_to_use
                    data_all['weight'] = event_weight[select]

                    c = c + 1
                else:
                    data2 = pd.DataFrame(data['gen_Hpt'][select])
                    data2['sample'] = sample_to_use
                    data2['weight'] = event_weight[select]

                    data_all = pd.concat([data_all, data2])

            print("------------------------------------------------------------")

        data_all.to_csv(f'{odir}/data_{ch}_{tag}.csv')


def main(args):
    # append '_year' to the output directory
    odir = args.odir + '_' + args.year
    if not os.path.exists(odir):
        os.makedirs(odir)

    # make subdirectory specefic to this script
    if not os.path.exists(odir + '/extra/'):
        os.makedirs(odir + '/extra/')
    odir = odir + '/extra'

    channels = args.channels.split(',')

    # get samples to make histograms
    f = open(args.samples)
    json_samples = json.load(f)
    f.close()

    # build samples
    samples = {}
    samples[args.year] = {}
    for ch in channels:
        samples[args.year][ch] = []
        for key, value in json_samples[args.year][ch].items():
            if value == 1:
                samples[args.year][ch].append(key)

    make_big_dataframe(args.year, channels, args.idir, odir, samples, args.tag)


if __name__ == "__main__":
    # e.g. run locally as
    # python get_var_for_plotting.py --year 2017 --odir plots --channels ele,mu --idir /eos/uscms/store/user/cmantill/boostedhiggs/Jun20_2017/ --tag gen_Hpt_with_iso

    parser = argparse.ArgumentParser()
    parser.add_argument('--year',            dest='year',        default='2017',                             help="year")
    parser.add_argument('--samples',         dest='samples',     default="plot_configs/samples_pfnano_value.json", help='path to json with samples to be plotted')
    parser.add_argument('--channels',        dest='channels',    default='ele,mu,had',                       help='channels for which to plot this variable')
    parser.add_argument('--odir',            dest='odir',        default='hists',                            help="tag for output directory... will append '_{year}' to it")
    parser.add_argument('--idir',            dest='idir',        default='../results/',                      help="input directory with results")
    parser.add_argument('--tag',             dest='tag',        default='',                      help="input directory with results")

    args = parser.parse_args()

    main(args)
