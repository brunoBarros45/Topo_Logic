type Listener = (...args: unknown[]) => void;

export class EventEmitter {
  static EventEmitter = EventEmitter;
  static defaultMaxListeners = 10;

  private events = new Map<string | symbol, Listener[]>();
  private maxListeners = EventEmitter.defaultMaxListeners;

  setMaxListeners(n: number): this {
    this.maxListeners = n;
    return this;
  }

  getMaxListeners(): number {
    return this.maxListeners;
  }

  addListener(event: string | symbol, listener: Listener): this {
    return this.on(event, listener);
  }

  on(event: string | symbol, listener: Listener): this {
    const list = this.events.get(event) ?? [];
    list.push(listener);
    this.events.set(event, list);
    return this;
  }

  once(event: string | symbol, listener: Listener): this {
    const wrapper: Listener = (...args: unknown[]) => {
      this.off(event, wrapper);
      listener(...args);
    };
    return this.on(event, wrapper);
  }

  off(event: string | symbol, listener: Listener): this {
    return this.removeListener(event, listener);
  }

  removeListener(event: string | symbol, listener: Listener): this {
    const list = this.events.get(event);
    if (!list) return this;
    const filtered = list.filter((item) => item !== listener);
    if (filtered.length === 0) {
      this.events.delete(event);
    } else {
      this.events.set(event, filtered);
    }
    return this;
  }

  removeAllListeners(event?: string | symbol): this {
    if (event === undefined) {
      this.events.clear();
    } else {
      this.events.delete(event);
    }
    return this;
  }

  emit(event: string | symbol, ...args: unknown[]): boolean {
    const list = this.events.get(event);
    if (!list || list.length === 0) return false;
    for (const listener of [...list]) {
      listener(...args);
    }
    return true;
  }

  listeners(event: string | symbol): Listener[] {
    return [...(this.events.get(event) ?? [])];
  }

  listenerCount(event: string | symbol): number {
    return this.events.get(event)?.length ?? 0;
  }

  eventNames(): Array<string | symbol> {
    return [...this.events.keys()];
  }
}

export default EventEmitter;
