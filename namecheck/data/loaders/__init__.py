"""Loader registry: name -> loader class."""
from namecheck.data.loaders.names_dataset import NamesDatasetLoader
from namecheck.data.loaders.wikidata import WikidataLoader
from namecheck.data.loaders.wikidata_ko import WikidataKoLoader
from namecheck.data.loaders.jmnedict import JmnedictLoader
from namecheck.data.loaders.corrections import CorrectionsLoader
from namecheck.data.loaders.tvlk_bookings import TvlkBookingsLoader
from namecheck.data.loaders.popular_names import PopularNamesLoader
from namecheck.data.loaders.kr_given_names import KrGivenNamesLoader
from namecheck.data.loaders.aliases import AliasesLoader
from namecheck.data.loaders.syllables import SyllablesLoader
from namecheck.data.loaders.surnames import SurnamesLoader
from namecheck.data.loaders.confusions import ConfusionsLoader
from namecheck.data.loaders.name_models import NameModelsLoader

REGISTRY = {
    cls.name: cls
    for cls in (
        NamesDatasetLoader, WikidataLoader, WikidataKoLoader, JmnedictLoader,
        CorrectionsLoader, TvlkBookingsLoader, PopularNamesLoader,
        KrGivenNamesLoader, AliasesLoader,
        SyllablesLoader, SurnamesLoader, ConfusionsLoader, NameModelsLoader,
    )
}

# token sources contribute frequency; the rest are derived/mined/generated stages.
TOKEN_SOURCES = ["names_dataset", "wikidata", "wikidata_ko", "jmnedict",
                 "corrections", "tvlk_bookings", "popular_names",
                 "kr_given_names"]
