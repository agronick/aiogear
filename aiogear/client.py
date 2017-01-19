import asyncio
import logging
import uuid
import random
from functools import partial
from aiogear.packet import Type
from aiogear.mixin import GearmanProtocolMixin

logger = logging.getLogger(__name__)


class Client(GearmanProtocolMixin, asyncio.Protocol):
    def __init__(self, loop=None):
        super(Client, self).__init__(loop=loop)
        self.transport = None

        self.submit_job = partial(self._submit_job, Type.SUBMIT_JOB)
        self.submit_job_bg = partial(self._submit_job, Type.SUBMIT_JOB_BG)
        self.submit_job_high = partial(self._submit_job, Type.SUBMIT_JOB_HIGH)
        self.submit_job_high_bg = partial(self._submit_job, Type.SUBMIT_JOB_HIGH_BG)
        self.submit_job_low = partial(self._submit_job, Type.SUBMIT_JOB_LOW)
        self.submit_job_low_bg = partial(self._submit_job, Type.SUBMIT_JOB_LOW_BG)

        self.handles = {}

    @staticmethod
    def uuid():
        # 0x00 is used as delimiter in gearman protocol
        # replace it with random printable character.
        replacement = chr(random.randint(32, 126)).encode('ascii')
        return uuid.uuid4().bytes.replace(b'\0', replacement)

    def connection_made(self, transport):
        self.transport = transport

    async def _submit_job(self, packet, name, *args, **kwargs):
        uuid = kwargs.pop('uuid', None)
        if uuid is None:
            uuid = self.uuid()
        self.send(packet, name, uuid, *args)
        handle = await self.register_response(Type.JOB_CREATED)
        f = self.register_response(Type.WORK_COMPLETE)
        self.handles[handle] = f
        f.add_done_callback(lambda _: self.handles.pop(handle))
        return handle

    def submit_job_sched(self, name, dt, *args, **kwargs):
        sched_args = [str(int(x)) for x in dt.strftime('%M %H %d %m %w').split()]
        return self._submit_job(Type.SUBMIT_JOB_SCHED, name, *(sched_args + list(args)), **kwargs)

    def get_status(self, handle):
        self.send(Type.GET_STATUS, handle)
        return self.register_response(Type.STATUS_RES)

    def get_status_unique(self, uuid):
        self.send(Type.STATUS_RES_UNIQUE, uuid)
        return self.register_response(Type.STATUS_RES_UNIQUE)

    def option_req(self, option):
        self.send(Type.OPTION_REQ, option)
        return self.register_response(Type.OPTION_RES, Type.ERROR)

    def wait_job(self, handle):
        f = self.handles.get(handle)
        if not f:
            raise RuntimeError('Unable to find handle {}'.format(handle))
        return f