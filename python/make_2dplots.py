#!/usr/bin/python

from utils import axis_dict, add_samples, color_by_sample, signal_by_ch, data_by_ch
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


def make_2dplots(year, ch, idir, odir, samples, vars, x_bins, x_start, x_end, y_bins, y_start, y_end):
    """
    Makes 2D plots of two variables

    Args:
        year: string that represents the year the processed samples are from
        ch: string that represents the signal channel to look at... choices are ['ele', 'mu', 'had']
        idir: directory that holds the processed samples (e.g. {idir}/{sample}/outfiles/*_{ch}.parquet)
        odir: output directory to hold the hist object
        samples: the set of samples to run over (by default: the samples with key==1 defined in plot_configs/samples_pfnano.json)
        vars: a list of two variable names to plot against each other... see the full list of choices in plot_configs/vars.json
    """

    # Get luminosity of year
    f = open('../fileset/luminosity.json')
    luminosity = json.load(f)[year]
    f.close()
    print(f'Processing samples from year {year} with luminosity {luminosity}')

    # instantiates the histogram object
    hists = {}
    hists = hist2.Hist(
        hist2.axis.Regular(x_bins, x_start, x_end, name=vars[0], label=vars[0], flow=False),
        hist2.axis.Regular(y_bins, y_start, y_end, name=vars[1], label=vars[1], flow=False),
        hist2.axis.StrCategory([], name='samples', growth=True),
        hist2.axis.StrCategory([], name='cuts', growth=True)
    )

    # loop over the processed files and fill the histograms
    for sample in samples[year][ch]:
        print("------------------------------------------------------------")
        parquet_files = glob.glob(f'{idir}/{sample}/outfiles/*_{ch}.parquet')  # get list of parquet files that have been processed
        if len(parquet_files) != 0:
            print(f'Processing {ch} channel of {sample}')
        else:
            print(f'No processed files for {sample} are found')

        # Get xsection if sample is MC
        try:
            f = open('../fileset/xsec_pfnano.json')
            xsec = json.load(f)
            f.close()
            xsec = eval(str((xsec[sample])))
            # Get overall weighting of events
            xsec_weight = (xsec * luminosity) / (get_sum_sumgenweight(idir, year, sample))
        except:
            xsec_weight = 1

        for i, parquet_file in enumerate(parquet_files):
            try:
                data = pq.read_table(parquet_file).to_pandas()
            except:
                print('Not able to read data: ', parquet_file, ' should remove evts from scaling/lumi')
                continue
            if len(data) == 0:
                continue

            # remove events with padded Nulls (e.g. events with no candidate jet will have a value of -1 for fj_pt)
            if ch != 'had':
                data = data[data['fj_pt'] != -1]

            try:
                event_weight = data['weight'].to_numpy()
            except:  # for data
                data['weight'] = 1  # for data fill a weight column with ones

            single_sample = None
            for single_key, key in add_samples.items():
                if key in sample:
                    single_sample = single_key

            # combining all pt bins of a specefic process under one name
            if single_sample is not None:
                hists.fill(
                    data[vars[0]],
                    data[vars[1]],
                    single_sample,
                    cuts='preselection',
                    weight=xsec_weight * data['weight']
                )
                if ch != 'had':
                    hists.fill(
                        data[vars[0]][data["anti_bjettag"] == 1][data["leptonInJet"] == 1],
                        data[vars[1]][data["anti_bjettag"] == 1][data["leptonInJet"] == 1],
                        single_sample,
                        cuts='btagdr',
                        weight=xsec_weight * data['weight'][data["anti_bjettag"] == 1][data["leptonInJet"] == 1]
                    )
            # otherwise give unique name
            else:
                hists.fill(
                    data[vars[0]],
                    data[vars[1]],
                    sample,
                    cuts='preselection',
                    weight=xsec_weight * data['weight']
                )
                if ch != 'had':
                    hists.fill(
                        data[vars[0]][data["anti_bjettag"] == 1][data["leptonInJet"] == 1],
                        data[vars[1]][data["anti_bjettag"] == 1][data["leptonInJet"] == 1],
                        sample,
                        cuts='btagdr',
                        weight=xsec_weight * data['weight'][data["anti_bjettag"] == 1][data["leptonInJet"] == 1]
                    )

    print("------------------------------------------------------------")

    with open(f'{odir}/{ch}_{vars[0]}_{vars[1]}.pkl', 'wb') as f:  # saves the hists objects
        pkl.dump(hists, f)


def plot_2dplots(year, ch, odir, vars, cut='preselection'):
    """
    Plots 2D plots of two variables that were made by "make_2dplots" function

    Args:
        year: string that represents the year the processed samples are from
        ch: string that represents the signal channel to look at... choices are ['ele', 'mu', 'had']
        odir: output directory to hold the plots
        vars: a list of two variable names to plot against each other... see the full list of choices in plot_configs/vars.json
        cut: the cut to apply when plotting the histogram... choices are ['preselection', 'btagdr'] for leptonic channel and ['preselection'] for hadronic channel
    """

    print(f'plotting for {cut} cut')

    # load the hists
    with open(f'{odir}/{ch}_{vars[0]}_{vars[1]}.pkl', 'rb') as f:
        hists = pkl.load(f)
        f.close()

    # make directory to store stuff per year
    if not os.path.exists(f'{odir}/{vars[0]}_{vars[1]}'):
        os.makedirs(f'{odir}/{vars[0]}_{vars[1]}')

    # make plots per channel
    for sample in hists.axes[2]:
        # one for log z-scale
        fig, ax = plt.subplots(figsize=(8, 5))
        hep.hist2dplot(hists[{'samples': sample, 'cuts': cut}], ax=ax, cmap="plasma", norm=matplotlib.colors.LogNorm(vmin=1e-3, vmax=1000))
        ax.set_xlabel(f"{vars[0]}")
        ax.set_ylabel(f"{vars[1]}")
        ax.set_title(f'{ch} channel for \n {sample} \n with {cut} cut')
        hep.cms.lumitext(f"{year} (13 TeV)", ax=ax)
        hep.cms.text("Work in Progress", ax=ax)
        plt.savefig(f'{odir}/{vars[0]}_{vars[1]}/{ch}_{sample}_{cut}_log_z.pdf')
        plt.close()

        # one for non-log z-scale
        fig, ax = plt.subplots(figsize=(8, 5))
        hep.hist2dplot(hists[{'samples': sample, 'cuts': cut}], ax=ax, cmap="plasma")
        ax.set_xlabel(f"{vars[0]}")
        ax.set_ylabel(f"{vars[1]}")
        ax.set_title(f'{ch} channel for \n {sample} \n with {cut} cut')
        hep.cms.lumitext(f"{year} (13 TeV)", ax=ax)
        hep.cms.text("Work in Progress", ax=ax)
        plt.savefig(f'{odir}/{vars[0]}_{vars[1]}/{ch}_{sample}_{cut}.pdf')
        plt.close()


def main(args):

    # append '_year' to the output directory
    odir = args.odir + '_' + args.year
    if not os.path.exists(odir):
        os.makedirs(odir)

    # make subdirectory specefic to this script
    if not os.path.exists(odir + '/2d_plots/'):
        os.makedirs(odir + '/2d_plots/')
    odir = odir + '/2d_plots/'

    # get samples to make histograms
    f = open(args.samples)
    json_samples = json.load(f)
    f.close()

    # build samples
    samples = {}
    samples[args.year] = {}
    samples[args.year][args.channel] = []
    for key, value in json_samples[args.year][args.channel].items():
        if value == 1:
            samples[args.year][args.channel].append(key)

    vars = args.vars.split(',')
    print(f'The 2 variables for cross check are: {vars}')

    if args.channel == 'had':
        cuts = ['preselection']
    else:
        cuts = ['preselection', 'btagdr']

    if args.make_hists:
        print('Making histograms...')
        make_2dplots(args.year, args.channel, args.idir, odir, samples, vars, args.x_bins, args.x_start, args.x_end, args.y_bins, args.y_start, args.y_end)

    if args.plot_hists:
        print('Plotting histograms...')
        for cut in cuts:
            plot_2dplots(args.year, args.channel, odir, vars, cut)


if __name__ == "__main__":
    # e.g. run locally as
    # lep_pt vs lep_iso:   python make_2dplots.py --year 2017 --odir hists --channel ele --vars lep_pt,lep_isolation --make_hists --plot_hists --x_bins 100 --x_start 0 --x_end 500 --y_bins 100 --y_start 0 --y_end 1 --idir /eos/uscms/store/user/fmokhtar/boostedhiggs/
    # lep_pt vs lep_fj_dr: python make_2dplots.py --year 2017 --odir hists --channel ele --vars lep_pt,lep_fj_dr     --make_hists --plot_hists --x_bins 100 --x_start 0 --x_end 500 --y_bins 100 --y_start 0 --y_end 2 --idir /eos/uscms/store/user/fmokhtar/boostedhiggs/
    # lep_pt vs mt:        python make_2dplots.py --year 2017 --odir hists --channel ele --vars lep_pt,lep_met_mt    --make_hists --plot_hists --x_bins 100 --x_start 0 --x_end 500 --y_bins 100 --y_start 0 --y_end 500 --idir /eos/uscms/store/user/fmokhtar/boostedhiggs/
    # lep_pt vs fj_pt:     python make_2dplots.py --year 2017 --odir hists --channel ele --vars lep_pt,fj_pt         --make_hists --plot_hists --x_bins 100 --x_start 0 --x_end 500 --y_bins 100 --y_start 0 --y_end 500 --idir /eos/uscms/store/user/fmokhtar/boostedhiggs/

    parser = argparse.ArgumentParser()
    parser.add_argument('--year',            dest='year',       default='2017',                                 help="year")
    parser.add_argument('--samples',         dest='samples',     default="plot_configs/samples_pfnano.json",     help="path to json with samples to be plotted")
    parser.add_argument('--channel',         dest='channel',     default='ele',                                  help="channel... choices are ['ele', 'mu', 'had']")
    parser.add_argument('--odir',            dest='odir',        default='hists',                                help="tag for output directory... will append '_{year}' to it")
    parser.add_argument('--idir',            dest='idir',        default='../results/',                          help="input directory with results")
    parser.add_argument('--vars',            dest='vars',        default='lep_pt,lep_isolation',                 help="channels for which to plot this variable")
    parser.add_argument('--x_bins',          dest='x_bins',      default=50,                                     help="binning of the first variable passed",                type=int)
    parser.add_argument('--x_start',         dest='x_start',     default=0,                                      help="starting range of the first variable passed",         type=int)
    parser.add_argument('--x_end',           dest='x_end',       default=1,                                      help="end range of the first variable passed",              type=int)
    parser.add_argument('--y_bins',          dest='y_bins',      default=50,                                     help="binning of the second variable passed",               type=int)
    parser.add_argument('--y_start',         dest='y_start',     default=0,                                      help="starting range of the second variable passed",        type=int)
    parser.add_argument('--y_end',           dest='y_end',       default=1,                                      help="end range of the second variable passed",             type=int)
    parser.add_argument("--make_hists",      dest='make_hists',  action='store_true',                            help="Make hists")
    parser.add_argument("--plot_hists",      dest='plot_hists',  action='store_true',                            help="Plot the hists")

    args = parser.parse_args()

    main(args)
