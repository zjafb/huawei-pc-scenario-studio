"""One request/deadline budget shared by writing, repair and review."""
import copy,time
from connectors import ConnectorError


class BudgetedModel:
    def __init__(self,client,run,limit=4,seconds=120,on_wait=None):
        self.client=client;self.run=run;self.limit=limit;self.deadline=time.monotonic()+seconds
        self.purpose='创作';run['model_calls']=[];run['model_request_limit']=limit
        self.on_wait=on_wait

    def __getattr__(self,name):return getattr(self.client,name)

    def chat_json(self,*args,**kwargs):
        retries=0
        while True:
            try:
                return self._attempt(*args,**kwargs)
            except ConnectorError as error:
                if error.kind not in ('rate_limit','token_rate_limit'):raise
                # Each transport attempt consumes the same four-request budget.
                # Do not spend the last seconds waiting with no time to request.
                delay=max(5 * 2**retries,error.retry_after or 0)
                if len(self.run['model_calls'])>=self.limit or self.deadline-time.monotonic()<=delay+1:raise
                self.run['model_calls'][-1]['retry_wait_seconds']=delay
                if self.on_wait:self.on_wait(f'模型服务暂时限流，等待{delay:g}秒后重试（计入本次4次调用上限）')
                time.sleep(delay)
                retries+=1

    def _attempt(self,*args,**kwargs):
        calls=self.run['model_calls'];remaining=self.deadline-time.monotonic()
        if len(calls)>=self.limit or remaining<=0:
            raise ConnectorError('本次生成已达到调用或时间上限，已停止自动修订；请根据具体问题调整要求。',kind='request_budget')
        call={'purpose':self.purpose,'messages':copy.deepcopy(args[0])};calls.append(call)
        start=time.monotonic();old_timeout=getattr(self.client,'timeout',None)
        if old_timeout is not None:self.client.timeout=min(old_timeout,remaining)
        try:
            result=self.client.chat_json(*args,**kwargs);call['output']=copy.deepcopy(result)
            completion=getattr(self.client,'last_completion',None)
            if completion:call.update(request_id=completion.request_id,usage=completion.usage)
            return result
        except ConnectorError as error:
            call.update(failure_kind=error.kind,error=str(error),http_status=error.code,provider_code=error.provider_code)
            raise
        finally:
            call['duration_ms']=round((time.monotonic()-start)*1000)
            if old_timeout is not None:self.client.timeout=old_timeout
