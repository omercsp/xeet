from xeet.common import XeetException
from xeet.log import log_info
from typing import Any
from pydantic import BaseModel


class ResourceModel(BaseModel):
    value: Any
    name: str = ""
    pool: Any = None


class Resource:
    def __init__(self, model: ResourceModel, pool: "ResourcePool"):
        self.value = model.value
        self.name = model.name
        self.pool: "ResourcePool" = pool
        self.taken: bool = False

    def release(self):
        if self.pool:
            self.pool.release(self)


class ResourcePool:
    def __init__(self, name: str, resources: list[ResourceModel]):
        self.name = name
        self.resources = [Resource(r, self) for r in resources]
        self.resources_dict = {r.name: r for r in self.resources}
        self.resource_fifo = self.resources.copy()
        log_info(f"Resource pool '{name}' created with {len(self.resources)} resource(s)")

    def __len__(self):
        return len(self.resources)

    def free_count(self):
        return len(self.resource_fifo)

    def obtain(self, qualifier: list[str] | int = 1) -> list[Resource]:
        if isinstance(qualifier, int):
            return self._obtain_fifo(qualifier)
        return self._obtain_by_names(qualifier)

    def _obtain_fifo(self, count: int) -> list[Resource]:
        if len(self.resources) < count:
            raise XeetException(f"Resource pool '{self.name}' has only {len(self.resources)} "
                                f"resources, {count} requested")
        if len(self.resource_fifo) < count:
            return []
        ret = self.resource_fifo[:count]
        for r in ret:
            r.taken = True
        self.resource_fifo = self.resource_fifo[count:]
        return ret

    def _obtain_by_names(self, names: list[str]) -> list[Resource]:
        names_len = len(names)
        if len(self.resources) < len(names):
            raise XeetException(f"Resource pool '{self.name}' has only {len(self.resources)} "
                                f"resources, {names_len} requested")
        if len(self.resource_fifo) < names_len:
            return []
        try:
            ret = [self.resources_dict[name] for name in names]
        except KeyError as e:
            raise XeetException(f"Resource not found in pool '{self.name}' - {e.args[0]}")
        if any(r.taken for r in ret):
            return []

        for r in ret:
            r.taken = True
            r_fifo_idx = self.resource_fifo.index(r)
            self.resource_fifo.pop(r_fifo_idx)
        return ret

    def release(self, resource):
        self.resource_fifo.append(resource)
        resource.taken = False
