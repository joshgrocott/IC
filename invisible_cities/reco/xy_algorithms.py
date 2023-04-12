import sys
import numpy  as np
import pandas as pd

from .. core.core_functions  import weighted_mean_and_var
from .. core                 import system_of_units as units
from .. core.exceptions      import SipmEmptyList
from .. core.exceptions      import SipmZeroCharge
from .. core.exceptions      import SipmEmptyListAboveQthr
from .. core.exceptions      import SipmZeroChargeAboveQthr
from .. core.exceptions      import ClusterEmptyList
from .. core.configure       import check_annotations

from .. types.ic_types       import xy
from .. evm.event_model      import Cluster

from typing import Optional

def find_algorithm(algoname):
    if algoname in sys.modules[__name__].__dict__:
        return getattr(sys.modules[__name__], algoname)
    else:
        raise ValueError("The algorithm <{}> does not exist".format(algoname))

@check_annotations
def barycenter(pos : np.ndarray, qs : np.ndarray):
    """pos = column np.array --> (matrix n x 2)
       ([x1, y1],
        [x2, y2]
        ...
        [xs, ys])
       qs = vector (q1, q2...qs) --> (1xn)

        """

    if not len(pos)   : raise SipmEmptyList
    if np.sum(qs) == 0: raise SipmZeroCharge
    mu, var = weighted_mean_and_var(pos, qs, axis=0)
    # For uniformity of interface, all xy algorithms should return a
    # list of clusters. barycenter always returns a single clusters,
    # but we still want it in a list.
    return [Cluster(np.sum(qs), xy(*mu), xy(*var), len(qs))]

    #return [Cluster(sum(qs), XY(*mu), var, len(qs))]


def discard_sipms(sis, pos, qs):
    return np.delete(pos, sis, axis=0), np.delete(qs, sis)


def get_nearby_sipm_inds(cs, d, pos):
    """return indices of sipms less than d from (xc,yc)"""
    return np.where(np.linalg.norm(pos - cs, axis=1) <= d)[0]


def count_masked(cs, d, datasipm, is_masked):
    if is_masked is None: return 0

    pos = np.stack([datasipm.X.values, datasipm.Y.values], axis=1)
    indices = get_nearby_sipm_inds(cs, d, pos)
    return np.count_nonzero(~is_masked.astype(bool)[indices])


@check_annotations
def corona( pos             : np.ndarray
          , qs              : np.ndarray
          , all_sipms       : pd.DataFrame
          , Qthr            : float
          , Qlm             : float
          , lm_radius       : float
          , new_lm_radius   : float
          , msipm           : int
          , consider_masked : Optional[bool] = False):
    """
    corona creates a list of Clusters by
    first , identifying hottest_sipm, the sipm with max charge in qs (must be > Qlm)
    second, calling barycenter() on the pos and qs SiPMs within lm_radius of hottest_sipm to
            find new_local_maximum.
    third , calling barycenter() on all SiPMs within new_lm_radius of new_local_maximum
    fourth, recording the Cluster found by barycenter if the cluster contains at least msipm
    fifth , removing (nondestructively) the sipms contributing to that Cluster
    sixth , repeating 1-5 until there are no more SiPMs of charge > Qlm

    arguments:
    pos   = column np.array --> (matrix n x 2)
            ([x1, y1],
             [x2, y2],
             ...     ,
             [xs, ys])
    qs    = vector (q1, q2...qs) --> (1xn)
    Qthr  = charge threshold, ignore all SiPMs with less than Qthr pes
    Qlm   = charge threshold, every Cluster must contain at least one SiPM with charge >= Qlm
    msipm = minimum number of SiPMs in a Cluster
    pitch = distance between SiPMs
    lm_radius = radius, find new_local_maximum by taking the barycenter of SiPMs within
                lm_radius of the max sipm. new_local_maximum is new in the sense that the
                prev loc max was the position of hottest_sipm. (Then allow all SiPMs with
                new_local_maximum of new_local_maximum to contribute to the pos and q of the
                new cluster).

                ***In general lm_radius should typically be set to 0, or some value slightly
                larger than pitch or pitch*sqrt(2).***

                ---------
                    This kwarg has some physical motivation. It exists to try to partially
                compensate problem that the NEW tracking plane is not continuous even though light
                can be emitted by the EL at any (x,y). When lm_radius < pitch, the search for SiPMs
                that might contribute pos and charge to a new Cluster is always centered about
                the position of hottest_sipm. That is, SiPMs within new_lm_radius of
                hottest_sipm are taken into account by barycenter(). In contrast, when
                lm_radius = pitch or pitch*sqrt(2) the search for SiPMs contributing to the new
                cluster can be centered at any (x,y). Consider the case where at a local maximum
                there are four nearly equally 'hot' SiPMs. new_local_maximum would yield a pos,
                pos1, between these hot SiPMs. Searching for SiPMs that contribute to this
                cluster within new_lm_radius of pos1 might be better than searching searching for
                SiPMs  within new_lm_radius of hottest_sipm.
                    We should be aware that setting lm_radius to some distance greater than pitch,
                we allow new_local_maximum to assume any (x,y) but we also create the effect that
                depending on where new_local_maximum is, more or fewer SiPMs will be
                within new_lm_radius. This effect does not exist when lm_radius = 0
                    lm_radius can always be set to 0 mm, but setting it to 15 mm (slightly larger
                than 10mm * sqrt(2)), should not hurt.

    new_lm_radius = radius, find a new cluster by calling barycenter() on pos/qs of SiPMs within
                    new_lm_radius of new_local_maximum

    consider_masked  = true if masked SiPMs are considered

    returns
    c    : a list of Clusters

    Usage Example
    In order to create each Cluster from a 3x3 block of SiPMs (where the center SiPM has more
    charge than the others), one would call:
    corona(pos, qs, all_sipms,
           Qthr            =  K1 * units.pes,
           Qlm             =  K2 * units.pes,
           lm_radius       =  0  * units.mm , # must be 0
           new_lm_radius   =  15 * units.mm , # must be 10mm*sqrt(2) or some number slightly larger
           msipm           =  K3,
           consider_masked = True)
    """
    assert     lm_radius >= 0,     "lm_radius must be non-negative"
    assert new_lm_radius >= 0, "new_lm_radius must be non-negative"

    if not len(pos)   : raise SipmEmptyList
    if np.sum(qs) == 0: raise SipmZeroCharge

    masked = all_sipms.Active.values.astype(bool) if consider_masked else None

    above_threshold = np.where(qs >= Qthr)[0]            # Find SiPMs with qs at least Qthr
    pos, qs = pos[above_threshold], qs[above_threshold]  # Discard SiPMs with qs less than Qthr

    if not len(pos)   : raise SipmEmptyListAboveQthr
    if np.sum(qs) == 0: raise SipmZeroChargeAboveQthr

    c  = []
    # While there are more local maxima
    while len(qs) > 0:

        hottest_sipm = np.argmax(qs)       # SiPM with largest Q
        if qs[hottest_sipm] < Qlm: break   # largest Q remaining is negligible

        # find new local maximum of charge considering all SiPMs within lm_radius of hottest_sipm
        within_lm_radius  = get_nearby_sipm_inds(pos[hottest_sipm], lm_radius, pos)
        new_local_maximum = barycenter(pos[within_lm_radius], qs[within_lm_radius])[0].posxy

        # find the SiPMs within new_lm_radius of the new local maximum of charge
        within_new_lm_radius = get_nearby_sipm_inds(new_local_maximum, new_lm_radius, pos      )
        n_masked_neighbours  = count_masked        (new_local_maximum, new_lm_radius, all_sipms, masked)

        # if there are at least msipms within_new_lm_radius, taking
        # into account any masked channel, get the barycenter
        if len(within_new_lm_radius) >= msipm - n_masked_neighbours:
            c.extend(barycenter(pos[within_new_lm_radius], qs[within_new_lm_radius]))

        # delete the SiPMs contributing to this cluster
        pos, qs = discard_sipms(within_new_lm_radius, pos, qs)

    if not len(c): raise ClusterEmptyList

    return c
