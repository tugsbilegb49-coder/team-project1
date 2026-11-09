// Keep capture and its Python interpreter inside the camera bundle's TCC identity.
#import <Cocoa/Cocoa.h>
#import <AVFoundation/AVFoundation.h>
#include <Python.h>
#include <stdatomic.h>
#include <sys/stat.h>
#include <unistd.h>
#include <signal.h>

static NSString *activePermit;
static NSString *activeSession;
static BOOL sessionActive(void) {
    NSData *data=[NSData dataWithContentsOfFile:activePermit];
    if(!data)return NO;
    id value=[NSJSONSerialization JSONObjectWithData:data options:0 error:nil];
    if(![value isKindOfClass:[NSDictionary class]])return NO;
    id session=value[@"session"],pid=value[@"wrapper_pid"];
    return [session isKindOfClass:[NSString class]] && [session isEqualToString:activeSession] &&
        [pid isKindOfClass:[NSNumber class]] && [pid intValue]>1 && kill([pid intValue],0)==0;
}
static PyObject *active(PyObject *self,PyObject *args){return PyBool_FromLong(sessionActive());}

static NSString *permissionStatus(void) {
    switch([AVCaptureDevice authorizationStatusForMediaType:AVMediaTypeVideo]) {
        case AVAuthorizationStatusAuthorized:return @"authorized";
        case AVAuthorizationStatusDenied:return @"denied";
        case AVAuthorizationStatusRestricted:return @"restricted";
        default:return @"not_determined";
    }
}
static PyObject *status(PyObject *self,PyObject *args) {
    return PyUnicode_FromString(permissionStatus().UTF8String);
}
static PyObject *requestPermission(PyObject *self,PyObject *args) {
    if(!sessionActive()){PyErr_SetString(PyExc_KeyboardInterrupt,"Camera session ended.");return NULL;}
    if(![[NSBundle mainBundle] objectForInfoDictionaryKey:@"NSCameraUsageDescription"])
        return PyUnicode_FromString("missing_description");
    if(![permissionStatus() isEqualToString:@"not_determined"])return status(self,args);
    __block atomic_bool finished=false;
    [AVCaptureDevice requestAccessForMediaType:AVMediaTypeVideo completionHandler:^(BOOL granted){atomic_store(&finished,true);}];
    NSDate *deadline=[NSDate dateWithTimeIntervalSinceNow:60];
    while(!atomic_load(&finished) && deadline.timeIntervalSinceNow>0) {
        Py_BEGIN_ALLOW_THREADS
        [[NSRunLoop currentRunLoop] runUntilDate:[NSDate dateWithTimeIntervalSinceNow:.05]];
        Py_END_ALLOW_THREADS
        if(PyErr_CheckSignals()<0)return NULL;
        if(!sessionActive()){PyErr_SetString(PyExc_KeyboardInterrupt,"Camera session ended.");return NULL;}
    }
    return atomic_load(&finished)?status(self,args):PyUnicode_FromString("timeout");
}
static PyMethodDef methods[]={
    {"session_active",active,METH_NOARGS,"Whether the owning wrapper still permits this session."},
    {"permission_status",status,METH_NOARGS,"Read permission without opening a camera."},
    {"request_permission",requestPermission,METH_NOARGS,"Ask only after explicit camera consent."},
    {NULL,NULL,0,NULL}
};
static struct PyModuleDef module={PyModuleDef_HEAD_INIT,"_worktrack_camera_host",NULL,-1,methods};
PyMODINIT_FUNC PyInit__worktrack_camera_host(void){return PyModule_Create(&module);}

static BOOL record(NSString *path,NSString *session,int code,BOOL complete,NSString *phase) {
    NSDictionary *value=@{@"session":session,@"pid":@((int)getpid()),@"complete":@(complete),@"exit_code":@(code),@"phase":phase};
    NSData *data=[NSJSONSerialization dataWithJSONObject:value options:0 error:nil];
    if(![data writeToFile:path options:NSDataWritingAtomic error:nil])return NO;
    chmod(path.fileSystemRepresentation,0600);
    return YES;
}
int main(int argc,char *argv[]) {
    @autoreleasepool {
        NSDictionary *info=[NSBundle mainBundle].infoDictionary;
        if(argc>1 && strcmp(argv[1],"--host-info")==0) {
            NSData *data=[NSJSONSerialization dataWithJSONObject:@{
                @"bundle_id":info[@"CFBundleIdentifier"]?:@"",
                @"usage_description":info[@"NSCameraUsageDescription"]?:@"",
                @"permission":permissionStatus()} options:0 error:nil];
            fwrite(data.bytes,1,data.length,stdout);return 0;
        }
        if(argc<4 || strcmp(argv[1],"--session")!=0)return 64;
        NSString *session=[NSString stringWithUTF8String:argv[2]];
        if(![[NSUUID alloc] initWithUUIDString:session])return 64;
        NSString *root=info[@"WorkTrackProjectRoot"];
        NSString *path=[info[@"WorkTrackSessionDirectory"] stringByAppendingPathComponent:[session stringByAppendingString:@".json"]];
        activeSession=session;
        activePermit=[info[@"WorkTrackSessionDirectory"] stringByAppendingPathComponent:[session stringByAppendingString:@".permit.json"]];
        if(!root || !info[@"NSCameraUsageDescription"])return 78;
        if(!record(path,session,0,NO,@"opening_project"))return 74;
        if(!sessionActive()){record(path,session,130,YES,@"cancelled");return 130;}
        if(chdir(root.fileSystemRepresentation)!=0){record(path,session,74,YES,@"project_folder_denied");return 74;}
        record(path,session,0,NO,@"initializing_python");
        PyImport_AppendInittab("_worktrack_camera_host",PyInit__worktrack_camera_host);
        PyConfig config;PyConfig_InitPythonConfig(&config);
        PyStatus result=PyConfig_SetBytesString(&config,&config.program_name,[info[@"WorkTrackPython"] fileSystemRepresentation]);
        if(!PyStatus_Exception(result))result=PyConfig_SetBytesArgv(&config,argc-2,argv+2);
        if(!PyStatus_Exception(result))result=Py_InitializeFromConfig(&config);
        PyConfig_Clear(&config);
        int code;
        if(PyStatus_Exception(result)){code=70;fprintf(stderr,"Camera Python initialization failed.\n");}
        else if(!sessionActive()){Py_FinalizeEx();code=130;}
        else {record(path,session,0,NO,@"running_python");code=Py_RunMain();}
        record(path,session,code,YES,@"finished");
        return code;
    }
}
