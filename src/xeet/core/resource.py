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

    def release(self) -> None:
        if self.pool:
            self.pool.release(self)


# Notice: The pool is not thread-safe. If you need to use the pool in a multi-threaded environment,
# the calling layer should handle the synchronization.
class ResourcePool:
    def __init__(self, name: str, resources: list[ResourceModel]):
        self.name = name
        self.resources = [Resource(r, self) for r in resources]
        self.resources_dict = {r.name: r for r in self.resources}
        self.resource_fifo = self.resources.copy()
        log_info(f"Resource pool '{name}' created with {len(self.resources)} resource(s)")

    def __len__(self) -> int:
        return len(self.resources)

    def free_count(self) -> int:
        return len(self.resource_fifo)

    def obtain(self, qualifier: list[str] | int = 1) -> list[Resource]:
        if isinstance(qualifier, int):
            return self._obtain_fifo(qualifier)
        return self._obtain_by_names(qualifier)

    def _obtain_fifo(self, count: int) -> list[Resource]:
        if count <= 0:
            raise XeetException(f"Invalid resource count requested: {count}")
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
        # check uniqueness of names
        names_len = len(names)
        if names_len != len(set(names)):
            raise XeetException(
                f"Resource pool '{self.name}' - duplicate resource names in request")

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

    def release(self, resource) -> None:
        if not resource.taken:
            raise XeetException(f"Resource '{resource.name}' is not taken, cannot release")
        self.resource_fifo.append(resource)
        resource.taken = False
