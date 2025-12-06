// mm/ml_predictor.c
#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/netlink.h>
#include <net/sock.h>
#include <linux/skbuff.h>
#include <linux/wait.h>
#include <linux/sched.h>
#include <linux/jiffies.h>
#include <linux/string.h>

#define NETLINK_PREDICT 31   /* usuario: 31 es un número arbitrario */
#define ML_TIMEOUT_MS 200    /* timeout para esperar respuesta (200 ms) */

static struct sock *nl_sk = NULL;
static int userspace_pid = 0;        /* portid del listener userspace */
static int ml_last_prediction = -1;  /* último valor recibido */
static int ml_response_ready = 0;
static DECLARE_WAIT_QUEUE_HEAD(ml_wq);

/* Handler que recibe mensajes desde userspace (bridge) */
static void ml_nl_recv(struct sk_buff *skb)
{
    struct nlmsghdr *nlh;
    int ret;
    int msg_len;

    if (!skb)
        return;

    nlh = nlmsg_hdr(skb);
    msg_len = nlmsg_len(nlh);

    /* Si el mensaje es un registro (userspace se presenta), guardamos portid */
    /* Aqui definimos: si msg_len == 0 => registro; si msg_len == sizeof(int) => respuesta */
    if (msg_len == 0) {
        userspace_pid = nlh->nlmsg_pid; /* portid del userspace */
        pr_info("ml_predictor: userspace registered pid=%d\n", userspace_pid);
        return;
    }

    /* Si el mensaje tiene sizeof(int), lo tratamos como respuesta de predicción */
    if (msg_len >= (int)sizeof(int)) {
        memcpy(&ml_last_prediction, nlmsg_data(nlh), sizeof(int));
        ml_response_ready = 1;
        wake_up_interruptible(&ml_wq);
        pr_info("ml_predictor: received prediction=%d from userspace\n", ml_last_prediction);
        return;
    }

    pr_warn("ml_predictor: received unexpected netlink message len=%d\n", msg_len);
}

/* Inicializar netlink (llamado en módulo init) */
static int __init ml_nl_init(void)
{
    struct netlink_kernel_cfg cfg = {
        .input = ml_nl_recv,
    };

    nl_sk = netlink_kernel_create(&init_net, NETLINK_PREDICT, &cfg);
    if (!nl_sk) {
        pr_err("ml_predictor: netlink_kernel_create failed\n");
        return -ENOMEM;
    }
    pr_info("ml_predictor: netlink created (proto=%d)\n", NETLINK_PREDICT);
    return 0;
}

/* Liberar netlink (módulo exit) */
static void __exit ml_nl_exit(void)
{
    if (nl_sk)
        netlink_kernel_release(nl_sk);
    pr_info("ml_predictor: netlink released\n");
}

/*
 * ml_send_features: enviar 5 floats (20 bytes) al userspace registrado,
 * luego esperar la respuesta (int) con timeout. Devuelve predicción (>=0) o <0 error.
 */
int ml_send_features(const float features[5])
{
    struct sk_buff *skb;
    struct nlmsghdr *nlh;
    int len = sizeof(float) * 5;
    int ret;
    unsigned long timeout_jiffies;

    if (!nl_sk || !userspace_pid)
        return -ENOTCONN;

    /* reset estado y preparar buffer */
    ml_response_ready = 0;
    ml_last_prediction = -1;

    skb = nlmsg_new(len, GFP_KERNEL);
    if (!skb)
        return -ENOMEM;

    nlh = nlmsg_put(skb, 0, 0, NLMSG_DONE, len, 0);
    if (!nlh) {
        nlmsg_free(skb);
        return -ENOMEM;
    }

    memcpy(nlmsg_data(nlh), features, len);

    /* enviar al userspace registrado (unicast) */
    ret = nlmsg_unicast(nl_sk, skb, userspace_pid);
    if (ret < 0) {
        pr_err("ml_predictor: nlmsg_unicast failed: %d\n", ret);
        return ret;
    }

    /* esperar respuesta (timeout) */
    timeout_jiffies = msecs_to_jiffies(ML_TIMEOUT_MS);
    ret = wait_event_interruptible_timeout(ml_wq, ml_response_ready != 0, timeout_jiffies);
    if (ret == 0) {
        /* timeout */
        pr_warn("ml_predictor: timeout waiting prediction\n");
        return -ETIMEDOUT;
    } else if (ret < 0) {
        /* interrupted */
        pr_warn("ml_predictor: wait interrupted\n");
        return ret;
    }

    /* respuesta lista */
    return ml_last_prediction;
}

/* Export para usar desde readahead.c (si enlazas dentro del kernel) */
EXPORT_SYMBOL(ml_send_features);

module_init(ml_nl_init);
module_exit(ml_nl_exit);

MODULE_LICENSE("GPL");
MODULE_AUTHOR("ML Integrator");
MODULE_DESCRIPTION("Kernel netlink bridge for ML readahead predictor");
