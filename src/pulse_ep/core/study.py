from pulse_ep.core.epmap import EPMap


class Study:
    def __init__(
        self,
        name: str,
        epmaps: EPMap | list[EPMap] = None,
        vendor: str | None = None,
        provenance: dict | None = None,
        placed_points: list | None = None,
    ) -> None:
        self.name: str = name
        #: acquisition system this study came from ("carto", "ensite", …).
        self.vendor: str | None = vendor
        #: importer-supplied provenance (software / export versions, GUID …).
        self.provenance: dict | None = provenance
        #: study-level markers (ablations, landmarks, …); see PlacedPoint.
        self.placed_points: list = placed_points or []

        if epmaps is not None:
            if isinstance(epmaps, EPMap):
                self.epmaps: list[EPMap] = [epmaps]
            elif isinstance(epmaps, list) and all(isinstance(item, EPMap) for item in epmaps):
                self.epmaps: list[EPMap] = epmaps
            else:
                raise ValueError("Invalid epmaps object provided. Expected EPMap or List[EPMap].")
        else:
            self.epmaps: list[EPMap] = []

    def add_epmap(self, epmap: EPMap) -> None:
        if isinstance(epmap, EPMap):
            self.epmaps.append(epmap)
        else:
            raise ValueError("Invalid EPMap object provided.")
