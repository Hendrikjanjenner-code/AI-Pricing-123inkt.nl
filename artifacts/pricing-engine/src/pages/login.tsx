import { useEffect, useState } from "react";
import { useLocation } from "wouter";
import { useLoginUser, getGetCurrentUserQueryKey } from "@workspace/api-client-react";
import { setAuthToken } from "@/lib/auth";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Box, Info } from "lucide-react";
import { useToast } from "@/hooks/use-toast";

export default function Login() {
  const [, setLocation] = useLocation();
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [gebruikersnaam, setGebruikersnaam] = useState("");
  const [wachtwoord, setWachtwoord] = useState("");
  const [devAdminAvailable, setDevAdminAvailable] = useState(false);

  const loginMutation = useLoginUser();

  useEffect(() => {
    let cancelled = false;
    fetch("/api/auth/health")
      .then(r => (r.ok ? r.json() : null))
      .then(data => {
        if (!cancelled && data?.environment === "development" && data?.dev_admin_available) {
          setDevAdminAvailable(true);
        }
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const res = await loginMutation.mutateAsync({
        data: { username: gebruikersnaam, password: wachtwoord }
      });
      setAuthToken(res.token);
      await queryClient.resetQueries({ queryKey: getGetCurrentUserQueryKey() });
      setLocation("/");
    } catch (err: any) {
      toast({
        title: "Aanmelden mislukt",
        description: err?.data?.detail || err?.message || "Ongeldige inloggegevens",
        variant: "destructive",
      });
    }
  };

  return (
    <div className="min-h-screen w-full flex items-center justify-center bg-background">
      <Card className="w-[400px]">
        <CardHeader className="space-y-1 items-center">
          <div className="w-12 h-12 bg-primary rounded-xl flex items-center justify-center mb-4">
            <Box className="w-6 h-6 text-primary-foreground" />
          </div>
          <CardTitle className="text-2xl font-bold">AI Pricing Engine</CardTitle>
          <CardDescription>
            Voer uw inloggegevens in om het operationeel dashboard te openen
          </CardDescription>
        </CardHeader>
        <form onSubmit={handleSubmit}>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="gebruikersnaam">Gebruikersnaam</Label>
              <Input
                id="gebruikersnaam"
                placeholder="admin"
                required
                value={gebruikersnaam}
                onChange={e => setGebruikersnaam(e.target.value)}
                disabled={loginMutation.isPending}
                autoComplete="username"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="wachtwoord">Wachtwoord</Label>
              <Input
                id="wachtwoord"
                type="password"
                required
                value={wachtwoord}
                onChange={e => setWachtwoord(e.target.value)}
                disabled={loginMutation.isPending}
                autoComplete="current-password"
              />
            </div>
            {devAdminAvailable && (
              <div className="flex items-start gap-2 rounded-md border border-dashed border-muted-foreground/30 bg-muted/40 p-3 text-xs text-muted-foreground">
                <Info className="w-4 h-4 mt-0.5 shrink-0" />
                <span>
                  Development admin account available — inloggen met{" "}
                  <code className="font-mono">dev_admin</code> / <code className="font-mono">admin123</code>
                </span>
              </div>
            )}
          </CardContent>
          <CardFooter>
            <Button className="w-full" type="submit" disabled={loginMutation.isPending}>
              {loginMutation.isPending ? "Aanmelden..." : "Aanmelden"}
            </Button>
          </CardFooter>
        </form>
      </Card>
    </div>
  );
}
