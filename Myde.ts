import * as path from 'path';
import {
  DebugSession,
  InitializedEvent,
  TerminatedEvent,
  StoppedEvent,
  BreakpointEvent,
  OutputEvent,
  Thread,
  Source,
  Breakpoint,
} from 'vscode-debugadapter';
import { DebugProtocol } from 'vscode-debugprotocol';

class MyDebugSession extends DebugSession {
  private confirmedBreakpoints = new Map<string, Breakpoint>();
  // Store active session reference for external event sending if needed
  private static activeSession: MyDebugSession | undefined;

  public constructor() {
    super();
    MyDebugSession.activeSession = this;
  }

  // Utility to build unique key for breakpoints map
  private bpKey(file: string, line: number) {
    return `${file}:${line}`;
  }

  // Called when the debug session is initialized
  protected initializeRequest(
    response: DebugProtocol.InitializeResponse,
    args: DebugProtocol.InitializeRequestArguments
  ): void {
    response.body = {
      supportsConfigurationDoneRequest: true,
      supportsBreakpointLocationsRequest: true,
      supportsEvaluateForHovers: true,
      supportsStepBack: false,
      supportsDataBreakpoints: false,
      supportsConditionalBreakpoints: true,
      supportsFunctionBreakpoints: false,
    };
    this.sendResponse(response);
    this.sendEvent(new InitializedEvent());
  }

  // Example stub: handle setBreakpointsRequest from VSCode
  protected setBreakPointsRequest(
    response: DebugProtocol.SetBreakpointsResponse,
    args: DebugProtocol.SetBreakpointsArguments
  ): void {
    // VSCode sets breakpoints by calling here.
    // You would normally forward this to Indago or your backend.

    // For demo: Accept the breakpoints and send them back verified
    const src = args.source;
    const breakpoints = args.breakpoints || [];
    const result: Breakpoint[] = [];

    for (const bp of breakpoints) {
      const verifiedBp = new Breakpoint(true, bp.line, src);
      result.push(verifiedBp);

      // Save breakpoint internally for syncing if you want
      this.confirmedBreakpoints.set(this.bpKey(src.path!, bp.line), verifiedBp);
    }

    response.body = { breakpoints: result };
    this.sendResponse(response);
  }

  // Your method to update breakpoints from Indago full snapshot
  public updateBreakpointsFromIndago(
    sessionBps: { file: string; line: number; enabled: boolean }[]
  ) {
    if (!MyDebugSession.activeSession) return;
    const session = MyDebugSession.activeSession;

    // Step 1: Build set of new keys from Indago
    const incomingKeys = new Set<string>();
    for (const { file, line } of sessionBps) {
      incomingKeys.add(this.bpKey(file, line));
    }

    // Step 2: Remove breakpoints no longer in Indago snapshot
    for (const [bpKey, bp] of this.confirmedBreakpoints.entries()) {
      if (!incomingKeys.has(bpKey)) {
        session.sendEvent(new BreakpointEvent("removed", bp));
        this.confirmedBreakpoints.delete(bpKey);
      }
    }

    // Step 3: Add or update breakpoints from Indago snapshot
    for (const { file, line, enabled } of sessionBps) {
      const bpKey = this.bpKey(file, line);
      const existing = this.confirmedBreakpoints.get(bpKey);

      // Add new or update existing
      if (!existing || existing.verified !== enabled) {
        const bp = new Breakpoint(enabled, line, new Source(path.basename(file), file));
        this.confirmedBreakpoints.set(bpKey, bp);

        // Use "new" event because we removed old breakpoints
        session.sendEvent(new BreakpointEvent("new", bp));
      }
    }
  }

  // Example of stopping the debug session
  protected disconnectRequest(
    response: DebugProtocol.DisconnectResponse,
    args: DebugProtocol.DisconnectArguments
  ): void {
    this.sendResponse(response);
    this.sendEvent(new TerminatedEvent());
  }

  // Other debug requests (launch, evaluate, stepIn, etc.) go here...
}

export default MyDebugSession;
