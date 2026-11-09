#import <Cocoa/Cocoa.h>
#include <signal.h>

@interface WorkTrackDelegate : NSObject <NSApplicationDelegate>
@property (copy) NSString *root;
@property (copy) NSString *instance;
@property (strong) NSTask *helperTask;
@property BOOL ownsRunner;
@property BOOL starting;
@property BOOL quitRequested;
@end

@implementation WorkTrackDelegate
- (NSString *)helper:(NSString *)action error:(NSString **)message {
    NSString *python=[self.root stringByAppendingPathComponent:@".venv/bin/python"];
    BOOL installed=[[NSFileManager defaultManager] isExecutableFileAtPath:python];
    NSTask *task=[NSTask new];
    task.executableURL=[NSURL fileURLWithPath:installed?python:@"/usr/bin/env"];
    NSMutableArray *arguments=[NSMutableArray array];
    if(!installed)[arguments addObject:@"python3"];
    [arguments addObjectsFromArray:@[[self.root stringByAppendingPathComponent:@"desktop/app_control.py"],action,self.instance]];
    task.arguments=arguments;
    task.currentDirectoryURL=[NSURL fileURLWithPath:self.root];
    NSMutableDictionary *environment=[[[NSProcessInfo processInfo] environment] mutableCopy];
    environment[@"PATH"]=@"/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin";
    task.environment=environment;
    NSPipe *output=[NSPipe pipe],*errors=[NSPipe pipe];
    task.standardOutput=output;task.standardError=errors;
    NSError *failure=nil;
    if(![task launchAndReturnError:&failure]){*message=failure.localizedDescription;return nil;}
    self.helperTask=task;
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW,(int64_t)(20*NSEC_PER_SEC)),dispatch_get_global_queue(QOS_CLASS_UTILITY,0),^{
        if(task.running)[task terminate];
    });
    NSData *data=[[output fileHandleForReading] readDataToEndOfFile];
    NSData *errorData=[[errors fileHandleForReading] readDataToEndOfFile];
    [task waitUntilExit];
    if(task.terminationStatus!=0){*message=[[NSString alloc] initWithData:errorData encoding:NSUTF8StringEncoding];if(!(*message).length)*message=@"Startup дууссангүй. Start WorkTrack.command-аар нээгээд .runtime/app.log-ийг шалгана уу.";return nil;}
    return [[[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding] stringByTrimmingCharactersInSet:[NSCharacterSet whitespaceAndNewlineCharacterSet]];
}
- (void)openWeb:(id)sender {
    [[NSWorkspace sharedWorkspace] openURL:[NSURL URLWithString:@"http://127.0.0.1:5173"]];
}
- (void)applicationDidFinishLaunching:(NSNotification *)notification {
    self.root=[[NSBundle mainBundle] objectForInfoDictionaryKey:@"WorkTrackProjectRoot"];
    self.instance=[[[NSUUID UUID] UUIDString] lowercaseString];self.starting=YES;
    NSMenu *bar=[NSMenu new];NSMenuItem *menuItem=[NSMenuItem new];[bar addItem:menuItem];
    NSMenu *menu=[[NSMenu alloc] initWithTitle:@"WorkTrack"];
    NSMenuItem *open=[[NSMenuItem alloc] initWithTitle:@"WorkTrack нээх" action:@selector(openWeb:) keyEquivalent:@"o"];
    open.target=self;[menu addItem:open];[menu addItem:[NSMenuItem separatorItem]];
    [menu addItemWithTitle:@"WorkTrack хаах" action:@selector(terminate:) keyEquivalent:@"q"];
    menuItem.submenu=menu;NSApp.mainMenu=bar;
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED,0), ^{
        NSString *error=nil;NSString *result=[self helper:@"start" error:&error];
        dispatch_async(dispatch_get_main_queue(), ^{
            self.starting=NO;self.ownsRunner=[result isEqualToString:@"started"];
            if(self.quitRequested){if(self.ownsRunner){NSString *ignored=nil;[self helper:@"stop" error:&ignored];}[NSApp replyToApplicationShouldTerminate:YES];return;}
            if(!result){NSAlert *alert=[NSAlert new];alert.messageText=@"WorkTrack ассангүй";alert.informativeText=error?:@"Төслийн хавтас болон Python тохиргоогоо шалгана уу.";[alert runModal];[NSApp terminate:nil];}
            else if(!self.ownsRunner)[self openWeb:nil];
        });
    });
}
- (BOOL)applicationShouldHandleReopen:(NSApplication *)sender hasVisibleWindows:(BOOL)visible {
    if(!self.starting)[self openWeb:nil];return YES;
}
- (NSApplicationTerminateReply)applicationShouldTerminate:(NSApplication *)sender {
    // A helper may still be acquiring the launch lock. Wait for it, then stop only our instance.
    if(self.starting){
        self.quitRequested=YES;
        if(self.helperTask.running)[self.helperTask terminate];
        return NSTerminateLater;
    }
    if(self.ownsRunner){NSString *error=nil;[self helper:@"stop" error:&error];}
    return NSTerminateNow;
}
@end

int main(int argc,const char *argv[]){
    @autoreleasepool {
        NSApplication *application=[NSApplication sharedApplication];
        [application setActivationPolicy:NSApplicationActivationPolicyRegular];
        __attribute__((objc_precise_lifetime)) WorkTrackDelegate *delegate=[WorkTrackDelegate new];application.delegate=delegate;
        [application run];
    }
    return 0;
}
