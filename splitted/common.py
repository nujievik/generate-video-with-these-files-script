import re
from datetime import timedelta

import executor
import flags.merge
import type_convert
import merge.params
from . import params
import file_info.mkvtools
from flags.flags import MATCHINGS

def add_skips(linking=False):
    names = set()

    for flg in ['opening', 'ending']:
        if not flags.merge.bool_flag(flg):
            names.add(flg)

            for flg_short, flg_long in MATCHINGS['full'].items():
                if flg_long == flg:
                    name.add(flg_short)

    names.update({name.lower() for name in flags.merge.flag('rm_chapters', default_if_missing=True)})

    rm_linking = linking or not flags.merge.bool_flag('linking')

    for ind, name in enumerate(params.names):
        uid = params.uids[ind]
        if name.lower() in names or rm_linking and uid or uid in params.segments.get('skips_uid', set()):
            params.skips.add(ind)

def set_segment_info(mkvmerge_stdout):
    duration = None
    timestamps = re.findall(r'Timestamp used in split decision: (\d{2}:\d{2}:\d{2}\.\d{9})', mkvmerge_stdout)

    if len(timestamps) == 2:
        params.defacto_start = type_convert.str_to_timedelta(timestamps[0])
        params.defacto_end = type_convert.str_to_timedelta(timestamps[1])

    elif len(timestamps) == 1:
        timestamp = type_convert.str_to_timedelta(timestamps[0])

        if params.start > timedelta(0): #timestamp for start
            params.defacto_start = timestamp
            duration = file_info.mkvtools.get_file_info(params.segment, 'Duration:')
            params.defacto_end = params.defacto_start + duration

        else:
            params.defacto_start = timedelta(0)
            params.defacto_end = timestamp

    else:
        params.defacto_start = timedelta(0)
        params.defacto_end = duration = file_info.mkvtools.get_file_info(params.segment, 'Duration:')

    if duration and params.defacto_end <= params.end: #real playback <= track duration
        params.offset_end = timedelta(0)
    else:
        params.offset_end = params.defacto_end - params.end

    params.offset_start = params.defacto_start - params.start
    params.length = params.defacto_end - params.defacto_start

def split_file(repeat=True):
    command = [
        'mkvmerge', '-o', str(params.segment), '--split', f'parts:{params.start}-{params.end}', '--no-chapters',
        '--no-global-tags', '--no-subtitles', f'--{params.file_type}-tracks', f'{params.tid}'
    ]
    command.append('--no-audio') if params.file_type == 'video' else command.append('--no-video')
    command.append('--no-attachments') if not merge.params.orig_fonts else None
    command.append(str(params.source))

    if flags.merge.bool_flag('extended_log'):
        print(f"Extracting a segment of the {params.file_type} track from the file '{str(params.source)}'. "
              f"Executing the following command:\n{type_convert.command_to_print_str(command)}")

    set_segment_info(executor.execute(command))

    if repeat and any(td > params.ACCEPT_OFFSETS[params.file_type] for td in [params.offset_start, params.offset_end]):
        old_start, old_end = params.start, params.defacto_end - params.offset_end
        params.start = params.start - params.offset_start if params.start - params.offset_start > timedelta(0) else params.start
        params.end = params.end - params.offset_end

        split_file(repeat=False)
        params.offset_start = params.defacto_start - old_start
        params.offset_end = params.defacto_end - old_end

def merge_file_segments(segments):
    command = ['mkvmerge', '-o', str(params.retimed)]
    command.append(str(segments[0]))
    for segment in segments[1:]:
        command.append(f'+{str(segment)}')

    if flags.merge.bool_flag('extended_log'):
        print(f'Merging retimed {params.file_type} track segments. Executing the following command:\n'
              f'{type_convert.command_to_print_str(command)}')

    executor.execute(command, get_stdout=False)

def set_matching_keys(filepath, filegroup):
    merge.params.matching_keys[str(params.retimed)] = [filepath, filegroup, params.tid]

def get_uid_lengths():
    lengths = {'uid': {'chapters': timedelta(0), 'defacto': timedelta(0)},
               'nonuid': {'chapters': timedelta(0), 'defacto': timedelta(0)}}

    for ind in range(0, params.ind):
        key1 = 'uid' if params.uids[ind] == params.uids[params.ind] else 'nonuid'

        lengths[key1]['chapters'] += params.chap_ends[ind] - params.chap_starts[ind]
        if ind in params.indexes:
            lengths[key1]['defacto'] += params.ends[ind] - params.starts[ind]

    for key1 in ['uid', 'nonuid']:
        lengths[key1]['offset'] = lengths[key1]['defacto'] - lengths[key1]['chapters']

    return lengths

def extract_track():
    command = ['mkvextract', 'tracks', str(params.source), f'{params.tid}:{str(params.segment)}']

    if flags.merge.bool_flag('extended_log'):
        print(f"Extracting subtitles track {params.tid} from the file '{str(params.source)}'. Executing "
              f"the following command:\n {type_convert.command_to_print_str(command)}")

    executor.execute(command, get_stdout=False)
