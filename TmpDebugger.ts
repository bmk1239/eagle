import {
  DebugSession,
  InitializedEvent,
  TerminatedEvent,
  StoppedEvent,
  Thread,
  StackFrame,
  Scope,
  Variable
} from 'vscode-debugadapter';
import { DebugProtocol } from 'vscode-debugprotocol';

class MyDebugSession extends DebugSession {
  private static THREAD_ID = 1;

  public constructor() {
    super();
  }

  protected initializeRequest(
    response: DebugProtocol.InitializeResponse,
    args: DebugProtocol.InitializeRequestArguments
  ): void {
    response.body = {
      supportsEvaluateForHovers: true,
      supportsConfigurationDoneRequest: true
    };
    this.sendResponse(response);
    this.sendEvent(new InitializedEvent());
  }

  protected launchRequest(
    response: DebugProtocol.LaunchResponse,
    args: DebugProtocol.LaunchRequestArguments
  ): void {
    // Start the "program" (mocked here)
    this.sendResponse(response);
    // Pretend we hit a breakpoint
    this.sendEvent(new StoppedEvent('breakpoint', MyDebugSession.THREAD_ID));
  }

  protected setBreakPointsRequest(
    response: DebugProtocol.SetBreakpointsResponse,
    args: DebugProtocol.SetBreakpointsArguments
  ): void {
    // For simplicity, accept all breakpoints as valid
    const breakpoints = args.breakpoints?.map(bp => ({
      verified: true,
      line: bp.line
    })) || [];

    response.body = { breakpoints };
    this.sendResponse(response);
  }

  protected threadsRequest(
    response: DebugProtocol.ThreadsResponse
  ): void {
    response.body = {
      threads: [new Thread(MyDebugSession.THREAD_ID, 'Main Thread')]
    };
    this.sendResponse(response);
  }

  protected stackTraceRequest(
    response: DebugProtocol.StackTraceResponse,
    args: DebugProtocol.StackTraceArguments
  ): void {
    const stackFrames = [
      new StackFrame(1, 'dummyFunction', this.createSource('dummy.js'), 42, 0)
    ];

    response.body = {
      stackFrames,
      totalFrames: stackFrames.length
    };
    this.sendResponse(response);
  }

  protected scopesRequest(
    response: DebugProtocol.ScopesResponse,
    args: DebugProtocol.ScopesArguments
  ): void {
    response.body = {
      scopes: [
        new Scope('Local', 1, false)
      ]
    };
    this.sendResponse(response);
  }

  protected variablesRequest(
    response: DebugProtocol.VariablesResponse,
    args: DebugProtocol.VariablesArguments
  ): void {
    response.body = {
      variables: [
        new Variable('x', '123'),
        new Variable('y', '"hello"')
      ]
    };
    this.sendResponse(response);
  }

  protected evaluateRequest(
    response: DebugProtocol.EvaluateResponse,
    args: DebugProtocol.EvaluateArguments
  ): void {
    const expr = args.expression;
    response.body = {
      result: `eval: ${expr}`,
      variablesReference: 0
    };
    this.sendResponse(response);
  }
}

DebugSession.run(MyDebugSession);
