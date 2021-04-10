from dataclasses import dataclass
import os

import re
from typing import List, Sequence
from string import hexdigits
import mimetypes

from pymediainfo import MediaInfo

# media_info = MediaInfo.parse('my_video_file.mov')

ANIME_PATTERN = re.compile(r'^(?P<group>\[[^]]+])?(?P<name>.*?)(?P<tags>\[.+])+\.(?P<ext>[^.]+)$')

KNOWN_GROUPS = {'Erai-raws', 'HorribleSubs', 'FFF', 'Commie',
                'SallySubs', 'CBM', 'Fate-Akuma', 'niizk', 'OZC',
                'kuchikirukia', 'Evil_Genuis', 'illya_', 'Beatrice-Raws',
                'Zurako', 'NoobSubs', 'OTR', 'Orphan-fussoir', 'lleur',
                'REVO', 'deanzel', 'RH', 'FMA1394', 'R2JxR1', 'Elysium',
                'Afro', 'Kametsu', 'bxyh', 'BSS', 'NOP', 'Team Nanban',
                '35mm'}


class Token:

    def __init__(self, value: str) -> None:
        self.value = value

    def __repr__(self) -> str:
        return f'{type(self).__name__}({self.value!r})'

    def __hash__(self) -> int:
        return hash(self.value)

    def __eq__(self, other) -> bool:
        return isinstance(other, type(self)) and other.value == self.value


class Extension(Token):
    pass


class AudioQuality(Token):
    pass


class VideoQuality(Token):
    pass


class Source(Token):
    pass


class SubGroup(Token):
    pass


class RandomTag(Token):
    pass


class AudioLanguage(Token):
    pass


class SubtitlesLanguage(Token):
    pass


class Hash(Token):
    pass


class Title(Token):
    pass


class EpisodeNumber(Token):

    # noinspection PyMissingConstructor
    def __init__(self, value: int) -> None:
        self.value = value


def _is_source_tag(string: str) -> bool:
    return string.lower() in {'bluray', 'blu-ray', 'bd', 'bdrip', 'dvd',
                              'dvdrip', 'web', 'webrip', 'hdtv', 'hardsub',
                              'vrv'}


def _is_audio_tag(string: str) -> bool:
    if string.lower() in {'aac', 'ac3', 'flac', 'vorbis', 'dts',
                          'aac_5.1', 'dts-es', '2ch'}:
        return True
    if (len(string) == 3
            and string[0].isnumeric()
            and string[1] == '.'
            and string[2].isnumeric()):
        return True
    return False


def _is_language_tag(string: str) -> bool:
    return string.lower() in {'jp', 'en', 'dual'}


def _is_video_tag(string: str) -> bool:
    if string.lower() in {'hevc', 'hi10p', 'x264', 'x265', 'h264', '10bit'}:
        return True
    if string[:-1].isnumeric() and string[-1] == 'p':
        return True
    if string.count('x') == 1:
        width, height = string.split('x')
        if width.isnumeric() and height.isnumeric():
            return True
    return False


def _tokenise_tag(words: Sequence[str]):
    tokens = []
    unclassified = []

    for word in words:
        if _is_audio_tag(word):
            tokens.append(AudioQuality(word))
        elif _is_video_tag(word):
            tokens.append(VideoQuality(word))
        elif _is_source_tag(word):
            tokens.append(Source(word))
        elif _is_language_tag(word):
            print('WARNING: language tag in tag words ' + str(words))
            tokens.append(AudioLanguage(word))
        else:
            unclassified.append(word)

    if unclassified:
        raise RuntimeError(f'Unclassified: {unclassified}')

    return tokens


@dataclass
class Categorised:
    filename: str
    show_name: str
    group: str
    quality: str
    filetype: str


def _tokenise(string: str):
    to_tokenise = []
    tokens = []
    for tag in re.findall(r'\[[^]]+]', string):
        value: str = tag[1:-1]

        if value in KNOWN_GROUPS:
            tokens.append(SubGroup(value))
        elif len(value) == 8 and not (set(value) - set(hexdigits)):
            tokens.append(Hash(value))
        elif value == 'Multiple Subtitle':
            tokens.append(SubtitlesLanguage('Multiple'))
            tokens.append(SubtitlesLanguage('EN'))
        elif value == 'Dual Audio':
            tokens.append(AudioLanguage('EN'))
            tokens.append(AudioLanguage('JP'))
        elif (re.match(r'Disc \d', value)
              or re.match(r'v\d', value)
              or value in {'Directors Cut', 'Clean Screen'}):
            pass
        else:
            # Attempt to split on various chars
            success = True
            failures = []
            for char in (' ', ',', '-', '.', '_'):
                try:
                    tokens.extend(_tokenise_tag(value.split(char)))
                except RuntimeError as e:
                    failures.append(e)
                else:
                    break
            else:
                success = False
            if not success:
                print('[' + string + ']\n  ' + value + ' due to ' + str(failures))

        remainder, string = string.split(tag, maxsplit=1)
        remainder = remainder.rstrip()
        string = string.lstrip()

        if remainder:
            to_tokenise.append(remainder)
    if string:
        to_tokenise.append(string)

    if len(to_tokenise) == 1:
        match = re.match(r'^(?P<name>.+?) - E?(?P<episode>\d+)(\+E?(?P<second_episode>\d+))?(?P<version>v\d+)?(?P<special_tag> END)?$', to_tokenise[0])
        if match:
            d = match.groupdict()
            tokens.append(Title(d['name']))
            tokens.append(EpisodeNumber(int(d['episode'])))
            if d['second_episode'] is not None:
                tokens.append(EpisodeNumber(int(d['second_episode'])))
            to_tokenise = []

    return tokens, to_tokenise


def skip(string: str) -> bool:
    guessed_type, _ = mimetypes.guess_type(string)
    if guessed_type is not None:
        main, sub = guessed_type.split('/')
        return main != 'video'
    return True


def is_anime(string: str) -> bool:
    return ANIME_PATTERN.match(string) is not None and ' ' in string


def _test1():
    import os
    tokenz = set()
    to_tokenize = list()
    skipped = set()
    not_anime = set()
    for t in test:
        if categorise.skip(t):
            skipped.add(t.split('.')[-1])
            continue
        if not categorise.is_anime(t):
            not_anime.add(t)
            continue
        if t.endswith(('mp3', 'srt', 'rar', 'zip', 'jpg',
                       'png', 'torrent', 'invalid', 'sh',
                       'txt', 'md5', 'nfo', 'ac3', 'flac',
                       'pdf')):
            continue
        n, e = os.path.splitext(t)
        tokens, to_tokenise = categorise._tokenise(n)
        tokenz |= set(tokens)
        to_tokenize.append(to_tokenise)


def _move():
    pass
