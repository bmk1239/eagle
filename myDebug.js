import {
  LoggingDebugSession,
  InitializedEvent,
  StoppedEvent,
  OutputEvent,
} from 'vscode-debugadapter';
import { DebugSession, DebugProtocol } from 'vscode-debugprotocol';
import * as grpc from '@grpc/grpc-js';
import * as protoLoader from '@grpc/proto-loader';

const PROTO_PATH = __dirname + '/../grpc-server/debug.proto';
const pkgDef = protoLoader.loadSync(PROTO_PATH);
const grpcObj = grpc.loadPackageDefinition(pkgDef) as any;
const client = new grpcObj.DebugService('localhost:50051', grpc.credentials.createInsecure());

class MyDebugSession extends LoggingDebugSession {
  constructor() {
    super("debug.txt");

    this.setDebuggerLinesStartAt1(true);
    this.setDebuggerColumnsStartAt1(true);
  }

  protected initializeRequest(response: DebugProtocol.InitializeResponse, _args: DebugProtocol.InitializeRequestArguments): void {
    response.body = {
      supportsEvaluateForHovers: true,
    };
    this.sendResponse(response);
    this.sendEvent(new InitializedEvent());
  }

  protected launchRequest(response: DebugProtocol.LaunchResponse, args: any): void {
    client.Launch({ program: args.program }, (err: any, res: any) => {
      if (err) {
        this.sendEvent(new OutputEvent(`Error: ${err.message}\n`));
      } else {
        this.sendEvent(new OutputEvent(`${res.message}\n`));
        this.sendEvent(new StoppedEvent("entry", 1));
      }
      this.sendResponse(response);
    });
  }

  protected evaluateRequest(response: DebugProtocol.EvaluateResponse, args: DebugProtocol.EvaluateArguments): void {
    client.Evaluate({ expression: args.expression }, (err: any, res: any) => {
      response.body = {
        result: err ? `Error: ${err.message}` : res.result,
        variablesReference: 0
      };
      this.sendResponse(response);
    });
  }
}

DebugSession.run(MyDebugSession);