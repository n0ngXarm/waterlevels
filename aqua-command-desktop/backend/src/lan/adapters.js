import {CsvReadonlySource} from './csv-source.js';
/** Source boundary. No module here loads an OT driver or opens an OT connection. */
export class SimulatedRuntimeAdapter{
 constructor(store,sourceId){this.store=store;this.sourceId=sourceId;this.available=true;this.kind='simulated-runtime';this.simulated=true}
 read(){return this.store.pumps(this.sourceId)}
}
export class WinCCReadonlyAdapter{
 constructor(){this.available=false;this.kind='wincc-readonly';this.simulated=false}
 read(){throw Error('WinCC read-only adapter unavailable: requires separate authorization and approved runtime mechanism/format')}
}
export function runtimeAdapter(kind,store,sourceId,config={}){
 if(kind==='simulated-runtime')return new SimulatedRuntimeAdapter(store,sourceId);
 if(kind==='wincc-csv')return new CsvReadonlySource(config,store,sourceId);
 if(kind==='wincc-readonly')return new WinCCReadonlyAdapter();
 throw Error('Unknown source adapter');
}
