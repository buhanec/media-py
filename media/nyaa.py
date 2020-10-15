from dataclasses import dataclass
import datetime
from enum import Enum
from typing import List, Optional
from urllib.parse import parse_qs
from xml.etree import ElementTree as etree
from bs4 import BeautifulSoup

import requests

ATOM_NS = 'http://www.w3.org/2005/Atom'
NYAA_NS = 'https://nyaa.si/xmlns/nyaa'

etree.register_namespace('atom', ATOM_NS)
etree.register_namespace('nyaa', NYAA_NS)


def _find(e: etree.Element, path: str) -> etree.Element:
    return e.find(path, {'atom': ATOM_NS, 'nyaa': NYAA_NS})


class Filter(int, Enum):
    NO_FILTER = 0
    NO_REMAKES = 1
    TRUSTED_ONLY = 2

    def __str__(self) -> str:
        return str(self.value)


class Category(str, Enum):
    ALL_CATEGORIES = '0_0'

    ANIME = '1_0'
    ANIME_MUSIC_VIDEO = '1_1'
    ANIME_ENGLISH_TRANSLATED = '1_2'
    ANIME_NON_ENGLISH_TRANSLATED = '1_3'
    ANIME_RAW = '1_4'

    AUDIO = '2_0'
    AUDIO_LOSSLESS = '2_1'
    AUDIO_LOSSY = '2_2'

    LITERATURE = '3_0'
    LITERATURE_ENGLISH_TRANSLATED = '3_1'
    LITERATURE_NON_ENGLISH_TRANSLATED = '3_2'
    LITERATURE_RAW = '3_3'

    LIVE_ACTION = '4_0'
    LIVE_ACTION_ENGLISH_TRANSLATED = '4_1'
    LIVE_ACTION_IDOL_PROMOTIONAL_VIDEO = '4_2'
    LIVE_ACTION_NON_ENGLISH_TRANSLATED = '4_3'
    LIVE_ACTION_RAW = '4_4'

    PICTURES = '5_0'
    PICTURES_GRAPHICS = '5_1'
    PICTURES_PHOTOS = '5_2'

    SOFTWARE = '6_0'
    SOFTWARE_APPLICATIONS = '6_1'
    SOFTWARE_GAMES = '6_2'

    def __str__(self) -> str:
        return self.value


class Sort(str, Enum):
    COMMENDS = 'comments'
    SIZE = 'size'
    DATE = 'id'
    SEEDERS = 'seeders'
    LEECHERS = 'leechers'
    DOWNLOADS = 'downloads'

    def __str__(self) -> str:
        return self.value


class SortDirection(str, Enum):
    ASCENDING = 'asc'
    DESCENDING = 'desc'

    def __str__(self) -> str:
        return self.value


@dataclass
class Guid:
    link: str
    permalink: bool

    @property
    def id(self) -> int:
        return int(self.link.rsplit('/', maxsplit=1)[-1])


@dataclass(eq=False)
class Result:
    title: str
    link: str
    guid: Guid
    published: datetime.datetime
    seeders: int
    leechers: int
    downloads: Optional[int]
    info_hash: Optional[str]
    category: Category
    size: str
    comments: int
    trusted: bool
    remake: bool

    def __eq__(self, other):
        return (isinstance(other, Result)
                and self.title == other.title
                and self.link == other.link
                and self.guid == other.guid
                and self.published == other.published
                # and self.seeders == other.seeders
                # and self.leechers == other.leechers
                # and self.downloads == other.downloads
                and self.info_hash == other.info_hash
                and self.category == other.category
                and self.size == other.size
                and self.comments == other.comments
                and self.trusted == other.trusted
                and self.remake == other.remake)


def search(query: str,
           filter: int = Filter.NO_FILTER,
           category: str = Category.ALL_CATEGORIES,
           sort: str = Sort.DATE,
           sort_direction: str = SortDirection.DESCENDING,
           rss: bool = True,
           page: int = 1) -> List[Result]:
    r = requests.get('https://nyaa.si', params={
        'q': query,
        'f': filter,
        'c': category,
        's': sort,
        'o': sort_direction,
        'p': page,
        'page': 'rss' if rss else ''
    })
    r.raise_for_status()
    if rss:
        blob = etree.fromstring(r.text)
        result = []
        for item in blob.findall('channel/item'):
            guid = item.find('guid')
            result.append(
                Result(title=item.find('title').text,
                       link=item.find('link').text,
                       guid=Guid(guid.text, guid.attrib['isPermaLink'] == 'true'),
                       published=datetime.datetime.strptime(item.find('pubDate').text, '%a, %d %b %Y %H:%M:%S %z'),
                       seeders=int(_find(item, 'nyaa:seeders').text),
                       leechers=int(_find(item, 'nyaa:leechers').text),
                       downloads=int(_find(item, 'nyaa:downloads').text),
                       info_hash=_find(item, 'nyaa:infoHash').text,
                       category=Category(_find(item, 'nyaa:categoryId').text),
                       size=_find(item, 'nyaa:size').text,
                       comments=int(_find(item, 'nyaa:comments').text),
                       trusted=_find(item, 'nyaa:trusted').text == 'Yes',
                       remake=_find(item, 'nyaa:remake').text == 'Yes')
            )
        return result
    else:
        blob = BeautifulSoup(r.text, features='html.parser')

        # Build item names
        ths = blob.table.thead.find_all('th')
        keys = []
        for th in ths:
            try:
                keys.append(th['title'])
            except KeyError:
                keys.append(th.text.strip())
        keys.remove('Comments')

        # Map rows
        rows = blob.table.tbody.find_all('tr')
        results = []
        for row in rows:
            result_d = {}
            for key, td in zip(keys, row.find_all('td')):
                if key == 'Name':
                    # Unpack comments
                    comments = td.find('a', class_='comments')
                    if comments:
                        result_d['Comments'] = int(comments.text.strip())
                    else:
                        result_d['Comments'] = 0

                    # Get main link for guid and title
                    main_link = td.find_all('a')[-1]
                    result_d['Guid'] = Guid('https://nyaa.si' + main_link['href'], True)
                    value = main_link['title']
                elif key == 'Category':
                    value = Category(td.a['href'].split('=')[-1])
                elif key == 'Link':
                    torrent, magnet = td.find_all('a')
                    value = 'https://nyaa.si' + torrent['href']
                    magnet_qs = parse_qs(magnet['href'].split('?', maxsplit=1)[-1])
                    result_d['Info Hash'] = magnet_qs['xt'][0].split(':')[-1]
                elif key == 'In UTC':
                    value = datetime.datetime.fromtimestamp(int(td['data-timestamp']), tz=datetime.timezone.utc)
                else:
                    value = td.text.strip()
                result_d[key] = value
            r = Result(title=result_d['Name'],
                       link=result_d['Link'],
                       guid=result_d['Guid'],
                       published=result_d['In UTC'],
                       seeders=int(result_d['Seeders']),
                       leechers=int(result_d['Leechers']),
                       downloads=None,
                       info_hash=result_d['Info Hash'],
                       category=result_d['Category'],
                       size=result_d['Size'],
                       comments=result_d['Comments'],
                       trusted='success' in row['class'],
                       remake='danger' in row['class'])
            results.append(r)
        return results
